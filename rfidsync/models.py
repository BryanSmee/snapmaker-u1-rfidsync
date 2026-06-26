"""Domain models for parsing OpenSpool scan events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class OpenSpoolRecord:
    """A resolved OpenSpool scan: a channel paired with a tag payload."""

    channel: int
    payload: dict[str, Any] # TODO: Add proper structure for the payload, e.g. spool_id, filament_type, etc.

    @property
    def spool_id(self) -> int | None:
        """The Spoolman spool id from the payload, or ``None`` if absent/invalid."""
        value = self.payload.get("spool_id")
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def fingerprint(self) -> str:
        """Stable key identifying this (channel, spool) pair for dedup."""
        return json.dumps(
            {"channel": self.channel, "spool_id": self.spool_id},
            sort_keys=True,
        )


@dataclass
class PendingScanEvent:
    """A JSON payload awaiting the slot/channel line that follows it in the log."""

    started_line_no: int
    started_monotonic: float
    payload: dict[str, Any] | None = None

    def is_expired(
        self,
        current_line_no: int,
        now_monotonic: float,
        max_lines: int,
        max_age_seconds: float,
    ) -> bool:
        """True once too many lines or too much time has passed without a match."""
        return (
            current_line_no - self.started_line_no > max_lines
            or now_monotonic - self.started_monotonic > max_age_seconds
        )
