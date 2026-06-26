"""Polls the printer's ``openrfid.log`` through Moonraker and parses scans."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Callable

from .config import VALID_CHANNELS
from .models import OpenSpoolRecord, PendingScanEvent
from .moonraker import MoonrakerClient

logger = logging.getLogger(__name__)

OPEN_SPOOL_JSON_RE = re.compile(r"OpenSpool JSON payload:\s*(\{.*\})", re.IGNORECASE)
SLOT_RE = re.compile(r"on reader slot_(\d+)_reader", re.IGNORECASE)

LOG_ROOT = "logs"
LOG_PATH = "openrfid.log"


class OpenRFIDLogWatcher:
    """Streams new lines from the remote OpenRFID log and yields scan records."""

    def __init__(
        self,
        moonraker: MoonrakerClient,
        *,
        start_at_end: bool = True,
        event_max_lines: int = 120,
        event_max_age_seconds: float = 10.0,
        log_raw_lines: bool = False,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.moonraker = moonraker
        self.start_at_end = start_at_end
        self.event_max_lines = event_max_lines
        self.event_max_age_seconds = event_max_age_seconds
        self.log_raw_lines = log_raw_lines
        self._monotonic = monotonic

        self.line_no = 0
        self.lines_processed = 0
        self.initialized = False
        self.current_event: PendingScanEvent | None = None

        self._last_modified: float | None = None
        self._last_size: int | None = None

    def _changed(self) -> bool:
        """Use file metadata to skip downloading an unchanged log."""
        try:
            for info in self.moonraker.list_files(LOG_ROOT):
                if info.get("path") != LOG_PATH:
                    continue
                modified = info.get("modified")
                size = info.get("size")
                if self._last_modified == modified and self._last_size == size:
                    return False
                self._last_modified = modified
                self._last_size = size
                return True
            # File missing from the listing (rotated/deleted) - force a fetch.
            return True
        except Exception as exc:  # noqa: BLE001 - metadata is best-effort
            logger.debug("Metadata check failed, will fetch log: %s", exc)
            return True

    def _expire_event_if_needed(self) -> None:
        if self.current_event and self.current_event.is_expired(
            self.line_no,
            self._monotonic(),
            self.event_max_lines,
            self.event_max_age_seconds,
        ):
            logger.debug("Expiring incomplete NFC event at line=%s", self.line_no)
            self.current_event = None

    @staticmethod
    def _extract_slot(line: str) -> int | None:
        match = SLOT_RE.search(line)
        if not match:
            return None
        channel = int(match.group(1))
        return channel if channel in VALID_CHANNELS else None

    def _fetch_lines(self) -> list[str] | None:
        try:
            text = self.moonraker.read_file(LOG_ROOT, LOG_PATH)
        except Exception as exc:  # noqa: BLE001 - transient network errors
            logger.warning("Failed to fetch remote log: %s", exc)
            return None
        if text is None:
            return []
        return text.splitlines()

    def poll(self) -> list[OpenSpoolRecord]:
        """Return scan records found since the previous poll."""
        if self.initialized and not self._changed():
            return []

        lines = self._fetch_lines()
        if lines is None:
            return []

        if not self.initialized:
            self.initialized = True
            logger.info("Connected to remote log: %s/%s", LOG_ROOT, LOG_PATH)
            self._changed()  # capture metadata baseline
            self.lines_processed = len(lines) if self.start_at_end else 0

        # Log rotation/clearing: cursor is past the new end, so reset it.
        if len(lines) < self.lines_processed:
            logger.info("Remote log shrank (rotated). Resetting cursor.")
            self.lines_processed = 0

        results: list[OpenSpoolRecord] = []
        for line in lines[self.lines_processed :]:
            self.lines_processed += 1
            self.line_no += 1
            record = self._process_line(line.rstrip("\n"))
            if record is not None:
                results.append(record)
        return results

    def _process_line(self, line: str) -> OpenSpoolRecord | None:
        if self.log_raw_lines:
            logger.debug("LOG LINE: %s", line)

        self._expire_event_if_needed()

        # 1. Capture the JSON payload, then wait for the slot line that follows.
        json_match = OPEN_SPOOL_JSON_RE.search(line)
        if json_match:
            try:
                payload = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                logger.exception("Failed to parse OpenSpool payload: %r", line)
                return None
            self.current_event = PendingScanEvent(
                started_line_no=self.line_no,
                started_monotonic=self._monotonic(),
                payload=payload,
            )
            return None

        # 2. Pair a slot assignment with the most recent payload.
        slot = self._extract_slot(line)
        if slot is None:
            return None
        if self.current_event is None or self.current_event.payload is None:
            return None

        record = OpenSpoolRecord(channel=slot, payload=self.current_event.payload)
        logger.info(
            "Parsed OpenSpool scan: channel=%s spool_id=%s",
            record.channel,
            record.spool_id,
        )
        self.current_event = None
        return record
