"""Runtime configuration, loaded entirely from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

# Channels exposed by the Snapmaker U1 toolhead (extruder .. extruder3).
VALID_CHANNELS: frozenset[int] = frozenset({0, 1, 2, 3})


def _get_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None and value != "" else default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    """Immutable application configuration.

    Use :meth:`from_env` to build an instance from the process environment.
    """

    # --- Connectivity ---
    moonraker_url: str = "http://localhost:7125"
    spoolman_url: str = "http://spoolman:7912"
    moonraker_api_key: str | None = None

    # --- Spoolman / Moonraker config snippet values ---
    spoolman_sync_rate: int = 5

    # --- Reader behaviour ---
    poll_interval: float = 3.0
    start_at_end: bool = True

    # --- Logging ---
    log_level: str = "INFO"
    log_raw_lines: bool = False

    # --- Advanced tuning ---
    request_timeout: int = 30
    dedup_seconds: float = 10.0
    event_max_lines: int = 120
    event_max_age_seconds: float = 10.0
    assignment_retry_interval: float = 5.0

    # --- Boot-time installer ---
    install_configs: bool = True
    restart_klipper_after_install: bool = False

    @property
    def moonraker_base(self) -> str:
        """Moonraker base URL without a trailing slash."""
        return self.moonraker_url.rstrip("/")

    @property
    def spoolman_base(self) -> str:
        """Spoolman base URL without a trailing slash (no ``/api`` suffix)."""
        return self.spoolman_url.rstrip("/")

    @property
    def spoolman_api_base(self) -> str:
        """Spoolman REST API base, e.g. ``http://host:7912/api/v1``."""
        return f"{self.spoolman_base}/api/v1"

    @property
    def gcode_url(self) -> str:
        """Moonraker endpoint used to run G-code scripts."""
        return f"{self.moonraker_base}/printer/gcode/script"

    @classmethod
    def from_env(cls) -> "Config":
        """Build configuration from environment variables."""
        return cls(
            moonraker_url=_get_str("MOONRAKER_URL", cls.moonraker_url),
            spoolman_url=_get_str("SPOOLMAN_URL", cls.spoolman_url),
            moonraker_api_key=os.getenv("MOONRAKER_API_KEY") or None,
            spoolman_sync_rate=_get_int("SPOOLMAN_SYNC_RATE", cls.spoolman_sync_rate),
            poll_interval=_get_float("POLL_INTERVAL", cls.poll_interval),
            start_at_end=_get_bool("START_AT_END", cls.start_at_end),
            log_level=_get_str("LOG_LEVEL", cls.log_level).upper(),
            log_raw_lines=_get_bool("LOG_RAW_LINES", cls.log_raw_lines),
            request_timeout=_get_int("REQUEST_TIMEOUT", cls.request_timeout),
            dedup_seconds=_get_float("DEDUP_SECONDS", cls.dedup_seconds),
            event_max_lines=_get_int("EVENT_MAX_LINES", cls.event_max_lines),
            event_max_age_seconds=_get_float(
                "EVENT_MAX_AGE_SECONDS", cls.event_max_age_seconds
            ),
            assignment_retry_interval=_get_float(
                "ASSIGNMENT_RETRY_INTERVAL", cls.assignment_retry_interval
            ),
            install_configs=_get_bool("INSTALL_CONFIGS", cls.install_configs),
            restart_klipper_after_install=_get_bool(
                "RESTART_KLIPPER_AFTER_INSTALL", cls.restart_klipper_after_install
            ),
        )
