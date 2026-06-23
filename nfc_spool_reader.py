#!/usr/bin/env python3

import configparser
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

CONFIG_PATH = "/home/lava/printer_data/config/extended/spoolman_sync.cfg"

# --- Configuration Setup ---
config = configparser.ConfigParser()

try:
    if not os.path.exists(CONFIG_PATH):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        config["server"] = {
            "moonraker_url": "http://127.0.0.1:7125/printer/gcode/script",
            "spoolman_url": "http://spoolman-ip:7912/api/v1"
        }
        config["reader"] = {
            "openrfid_log": "/home/lava/printer_data/logs/openrfid.log",
            "poll_interval": "0.25",
            "start_at_end": "True"
        }
        config["logging"] = {
            "level": "INFO",
            "raw_lines": "False"
        }
        config["advanced"] = {
            "request_timeout": "30",
            "dedup_seconds": "10.0",
            "event_max_lines": "120",
            "event_max_age_seconds": "10.0",
            "assignment_retry_interval": "5.0"
        }
        with open(CONFIG_PATH, "w") as f:
            config.write(f)
    else:
        config.read(CONFIG_PATH)
except Exception as e:
    print(f"Warning: Could not read or create config file {CONFIG_PATH}: {e}")
    # Proceeding with defaults if config file fails

def get_config_val(section, key, fallback, getter=config.get):
    try:
        if config.has_option(section, key):
            return getter(section, key)
    except Exception:
        pass
    return fallback

# Load variables from config
OPENRFID_LOG = get_config_val("reader", "openrfid_log", "/home/lava/printer_data/logs/openrfid.log")
POLL_INTERVAL = get_config_val("reader", "poll_interval", 0.25, config.getfloat)
START_AT_END = get_config_val("reader", "start_at_end", True, config.getboolean)

MOONRAKER_GCODE_URL = get_config_val("server", "moonraker_url", "http://127.0.0.1:7125/printer/gcode/script")
SPOOLMAN_API_BASE = get_config_val("server", "spoolman_url", "http://spoolman-ip:7912/api/v1")

LOG_LEVEL = get_config_val("logging", "level", os.getenv("NFC_SPOOL_READER_LOG_LEVEL", "INFO")).upper()
LOG_RAW_LINES = get_config_val("logging", "raw_lines", os.getenv("NFC_SPOOL_READER_LOG_RAW_LINES", "0") == "1", config.getboolean)

REQUEST_TIMEOUT = get_config_val("advanced", "request_timeout", 30, config.getint)
DEDUP_SECONDS = get_config_val("advanced", "dedup_seconds", 10.0, config.getfloat)
EVENT_MAX_LINES = get_config_val("advanced", "event_max_lines", 120, config.getint)
EVENT_MAX_AGE_SECONDS = get_config_val("advanced", "event_max_age_seconds", 10.0, config.getfloat)
ASSIGNMENT_RETRY_INTERVAL = get_config_val("advanced", "assignment_retry_interval", 5.0, config.getfloat)

VALID_CHANNELS = {0, 1, 2, 3}

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("nfc_spool_reader")

OPEN_SPOOL_JSON_RE = re.compile(r"OpenSpool JSON payload:\s*(\{.*\})", re.IGNORECASE)
SLOT_RE = re.compile(r"on reader slot_(\d+)_reader", re.IGNORECASE)


@dataclass
class OpenSpoolRecord:
    channel: int
    payload: Dict[str, Any]

    @property
    def spool_id(self) -> Optional[int]:
        value = self.payload.get("spool_id")
        try:
            return None if value in (None, "") else int(value)
        except (TypeError, ValueError):
            return None

    def fingerprint(self) -> str:
        return json.dumps(
            {"channel": self.channel, "spool_id": self.spool_id},
            sort_keys=True,
        )


@dataclass
class PendingScanEvent:
    started_line_no: int
    started_monotonic: float
    payload: Optional[Dict[str, Any]] = None

    def is_expired(self, current_line_no: int, now_monotonic: float) -> bool:
        return (
            current_line_no - self.started_line_no > EVENT_MAX_LINES
            or now_monotonic - self.started_monotonic > EVENT_MAX_AGE_SECONDS
        )


class Deduper:
    def __init__(self, ttl_seconds: float):
        self.ttl_seconds = ttl_seconds
        self._seen: Dict[str, float] = {}

    def is_duplicate(self, key: str) -> bool:
        now = time.time()
        self._seen = {
            k: ts for k, ts in self._seen.items()
            if now - ts <= self.ttl_seconds
        }
        if key in self._seen:
            return True
        self._seen[key] = now
        return False


class MoonrakerClient:
    def __init__(self, gcode_url: str, timeout: int = REQUEST_TIMEOUT):
        self.gcode_url = gcode_url
        self.timeout = timeout
        self.session = requests.Session()

    def set_channel_spool(self, channel: int, spool_id: int) -> bool:
        script = f"SET_CHANNEL_SPOOL CHANNEL={channel} ID={spool_id}"
        logger.info("Sending gcode: %s", script)
        logger.debug(
            "POST %s payload=%r timeout=%s",
            self.gcode_url,
            {"script": script},
            self.timeout,
        )
        try:
            resp = self.session.post(
                self.gcode_url,
                json={"script": script},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            logger.info("Moonraker accepted gcode: %s", script)
            logger.debug("Moonraker response status=%s", resp.status_code)
            return True
        except requests.exceptions.Timeout:
            logger.warning("Timed out sending gcode: %s", script)
            return False
        except requests.exceptions.RequestException:
            logger.exception("HTTP error sending gcode: %s", script)
            return False


class SpoolmanClient:
    def __init__(self, base_url: str, timeout: int = REQUEST_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def spool_exists(self, spool_id: int) -> bool:
        url = f"{self.base_url}/spool/{spool_id}"
        logger.debug("Checking Spoolman spool_id=%s at %s", spool_id, url)
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                logger.debug("Spoolman confirmed spool_id=%s", spool_id)
                return True
            logger.warning(
                "Spool lookup failed: spool_id=%s url=%s status=%s body=%r",
                spool_id,
                url,
                resp.status_code,
                resp.text[:300],
            )
            return False
        except requests.exceptions.RequestException:
            logger.exception("Error checking spool_id=%s at %s", spool_id, url)
            return False


class OpenRFIDLogWatcher:
    def __init__(self, path: str, start_at_end: bool = True):
        self.path = path
        self.start_at_end = start_at_end
        self.fp = None
        self.line_no = 0
        self.current_event: Optional[PendingScanEvent] = None

    def open(self) -> None:
        self.fp = open(self.path, "r", encoding="utf-8", errors="replace")
        self.line_no = 0
        self.current_event = None
        if self.start_at_end:
            self.fp.seek(0, os.SEEK_END)
        logger.info("Watching log: %s", self.path)
        logger.debug("start_at_end=%s", self.start_at_end)

    def reopen_if_rotated(self) -> None:
        if self.fp is None:
            self.open()
            return
        try:
            if os.stat(self.path).st_ino != os.fstat(self.fp.fileno()).st_ino:
                logger.info("Log rotated, reopening %s", self.path)
                self.fp.close()
                self.fp = None
                self.open()
        except FileNotFoundError:
            logger.warning("Log file not found: %s", self.path)
            time.sleep(1)

    def _expire_event_if_needed(self) -> None:
        if self.current_event and self.current_event.is_expired(
            self.line_no, time.monotonic()
        ):
            logger.debug(
                "Expiring incomplete NFC event at line=%s",
                self.line_no,
            )
            self.current_event = None

    @staticmethod
    def _extract_slot(line: str) -> Optional[int]:
        match = SLOT_RE.search(line)
        if not match:
            return None
        try:
            channel = int(match.group(1))
        except ValueError:
            return None
        return channel if channel in VALID_CHANNELS else None

    def poll(self) -> List[OpenSpoolRecord]:
        self.reopen_if_rotated()
        if self.fp is None:
            return []

        results: List[OpenSpoolRecord] = []

        while True:
            line = self.fp.readline()
            if not line:
                break

            self.line_no += 1
            line = line.rstrip("\n")

            if LOG_RAW_LINES:
                logger.debug("LOG LINE: %s", line)

            self._expire_event_if_needed()

            # 1. Look for the JSON Payload first
            json_match = OPEN_SPOOL_JSON_RE.search(line)
            if json_match:
                try:
                    payload = json.loads(json_match.group(1))
                    self.current_event = PendingScanEvent(
                        started_line_no=self.line_no, 
                        started_monotonic=time.monotonic(), 
                        payload=payload
                    )
                    logger.debug("Captured JSON payload, waiting for slot assignment...")
                except Exception:
                    logger.exception("Failed to parse OpenSpool payload: %r", json_match.group(1))
                continue

            # 2. Look for the channel/slot assignment line that follows
            slot = self._extract_slot(line)
            if slot is not None:
                if self.current_event is None or self.current_event.payload is None:
                    logger.warning("Detected slot assignment (%s) but no JSON payload was captured recently", slot)
                    continue

                record = OpenSpoolRecord(channel=slot, payload=self.current_event.payload)
                logger.info(
                    "Parsed OpenSpool payload: channel=%s spool_id=%s",
                    record.channel,
                    record.spool_id,
                )
                logger.debug("Payload contents: %s", record.payload)
                results.append(record)
                self.current_event = None

        return results


class PendingAssignments:
    def __init__(self):
        self._pending: Dict[int, Dict[str, Any]] = {}

    def update(self, channel: int, spool_id: int) -> None:
        now = time.monotonic()
        existing = self._pending.get(channel)
        if existing and existing["spool_id"] == spool_id:
            existing["updated_at"] = now
            logger.info(
                "Channel %s already pending spool %s, keeping latest desired state",
                channel,
                spool_id,
            )
            logger.debug("Pending assignments: %r", self._pending)
            return

        self._pending[channel] = {
            "spool_id": spool_id,
            "updated_at": now,
            "last_attempt_at": 0.0,
        }
        logger.info("Queued assignment: channel %s -> spool %s", channel, spool_id)
        logger.debug("Pending assignments: %r", self._pending)

    def ready(self, retry_interval: float) -> List[tuple[int, int]]:
        now = time.monotonic()
        ready_items = [
            (channel, int(item["spool_id"]))
            for channel, item in self._pending.items()
            if now - item["last_attempt_at"] >= retry_interval
        ]
        if ready_items:
            logger.debug("Assignments ready for retry: %r", ready_items)
        return ready_items

    def mark_attempt(self, channel: int) -> None:
        if channel in self._pending:
            self._pending[channel]["last_attempt_at"] = time.monotonic()

    def mark_success(self, channel: int, spool_id: int) -> None:
        item = self._pending.get(channel)
        if item and int(item["spool_id"]) == spool_id:
            self._pending.pop(channel, None)
            logger.info(
                "Assignment applied successfully: channel %s -> spool %s",
                channel,
                spool_id,
            )
            logger.debug("Pending assignments after success: %r", self._pending)

    def has_pending(self) -> bool:
        return bool(self._pending)


class NFCSpoolReaderApp:
    def __init__(self):
        self.spoolman = SpoolmanClient(SPOOLMAN_API_BASE)
        self.moonraker = MoonrakerClient(MOONRAKER_GCODE_URL)
        self.watcher = OpenRFIDLogWatcher(OPENRFID_LOG, start_at_end=START_AT_END)
        self.deduper = Deduper(DEDUP_SECONDS)
        self.pending_assignments = PendingAssignments()

    def handle_record(self, record: OpenSpoolRecord) -> None:
        spool_id = record.spool_id
        if spool_id is None:
            logger.warning("Missing spool_id in payload, skipping: %s", record.payload)
            return

        if self.deduper.is_duplicate(record.fingerprint()):
            logger.info("Duplicate payload ignored: %s", record.fingerprint())
            return

        if not self.spoolman.spool_exists(spool_id):
            logger.warning("spool_id=%s not found in Spoolman, skipping", spool_id)
            return

        logger.info("Discovered assignment channel %d -> spool %d", record.channel, spool_id)
        self.pending_assignments.update(record.channel, spool_id)

    def flush_pending_assignments(self) -> None:
        if not self.pending_assignments.has_pending():
            return

        for channel, spool_id in self.pending_assignments.ready(ASSIGNMENT_RETRY_INTERVAL):
            logger.debug(
                "Attempting assignment channel=%s spool_id=%s",
                channel,
                spool_id,
            )
            self.pending_assignments.mark_attempt(channel)
            if self.moonraker.set_channel_spool(channel, spool_id):
                self.pending_assignments.mark_success(channel, spool_id)
            else:
                logger.warning(
                    "Moonraker busy/unavailable, keeping pending assignment "
                    "channel=%s spool_id=%s for retry",
                    channel,
                    spool_id,
                )

    def run(self) -> None:
        while not os.path.exists(OPENRFID_LOG):
            logger.warning("Waiting for log file: %s", OPENRFID_LOG)
            time.sleep(1)

        self.watcher.open()

        while True:
            try:
                for record in self.watcher.poll():
                    self.handle_record(record)

                self.flush_pending_assignments()

            except Exception:
                logger.exception("Watcher loop error - continuing")

            time.sleep(POLL_INTERVAL)


def main() -> None:
    logger.info("Starting NFC Spool Reader")
    logger.info("Using configuration from: %s", CONFIG_PATH)
    try:
        NFCSpoolReaderApp().run()
    except KeyboardInterrupt:
        logger.warning("NFC Spool Reader interrupted by user")
    except Exception:
        logger.exception("Fatal error in NFC Spool Reader")
        raise
    finally:
        logger.info("NFC Spool Reader shutting down")


if __name__ == "__main__":
    main()
