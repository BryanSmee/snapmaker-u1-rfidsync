"""Application wiring and the main poll loop."""

from __future__ import annotations

import logging
import time

from .assignments import Deduper, PendingAssignments
from .config import Config
from .installer import ConfigInstaller
from .models import OpenSpoolRecord
from .moonraker import MoonrakerClient
from .spoolman import SpoolmanClient
from .watcher import OpenRFIDLogWatcher

logger = logging.getLogger(__name__)


class NFCSpoolReaderApp:
    """Ties together the watcher, Spoolman validation and Klipper assignment."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.moonraker = MoonrakerClient(
            config.moonraker_base,
            timeout=config.request_timeout,
            api_key=config.moonraker_api_key,
        )
        self.spoolman = SpoolmanClient(
            config.spoolman_api_base, timeout=config.request_timeout
        )
        self.watcher = OpenRFIDLogWatcher(
            self.moonraker,
            start_at_end=config.start_at_end,
            event_max_lines=config.event_max_lines,
            event_max_age_seconds=config.event_max_age_seconds,
            log_raw_lines=config.log_raw_lines,
        )
        self.deduper = Deduper(config.dedup_seconds)
        self.pending_assignments = PendingAssignments()

    def handle_record(self, record: OpenSpoolRecord) -> None:
        """Validate a scan and queue the resulting channel assignment."""
        spool_id = record.spool_id
        if spool_id is None:
            logger.warning("Missing spool_id in payload, skipping: %s", record.payload)
            return

        if self.deduper.is_duplicate(record.fingerprint()):
            return

        if not self.spoolman.spool_exists(spool_id):
            logger.warning("spool_id=%s not found in Spoolman, skipping", spool_id)
            return

        self.pending_assignments.update(record.channel, spool_id)

    def flush_pending_assignments(self) -> None:
        """Try to apply any queued assignments that are due for a retry."""
        if not self.pending_assignments.has_pending():
            return

        for channel, spool_id in self.pending_assignments.ready(
            self.config.assignment_retry_interval
        ):
            self.pending_assignments.mark_attempt(channel)
            if self.moonraker.set_channel_spool(channel, spool_id):
                self.pending_assignments.mark_success(channel, spool_id)

    def tick(self) -> None:
        """Run a single poll iteration."""
        for record in self.watcher.poll():
            self.handle_record(record)
        self.flush_pending_assignments()

    def run(self) -> None:
        """Run the poll loop forever."""
        if self.config.install_configs:
            try:
                ConfigInstaller(self.moonraker, self.config).install()
            except Exception:
                logger.exception("Config install failed - continuing without it")

        while True:
            try:
                self.tick()
            except Exception:
                logger.exception("Watcher loop error - continuing")
            time.sleep(self.config.poll_interval)
