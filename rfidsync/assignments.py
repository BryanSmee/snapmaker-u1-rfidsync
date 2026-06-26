"""Deduplication and pending-assignment bookkeeping."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

# Injectable clocks make the time-based logic deterministic under test.
WallClock = Callable[[], float]
MonotonicClock = Callable[[], float]


class Deduper:
    """Suppresses repeated keys seen within a sliding TTL window."""

    def __init__(self, ttl_seconds: float, clock: WallClock = time.time) -> None:
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._seen: dict[str, float] = {}

    def is_duplicate(self, key: str) -> bool:
        """Record ``key`` and return whether it was already seen recently."""
        now = self._clock()
        self._seen = {
            k: ts for k, ts in self._seen.items() if now - ts <= self.ttl_seconds
        }
        if key in self._seen:
            return True
        self._seen[key] = now
        return False


@dataclass
class _PendingItem:
    spool_id: int
    updated_at: float
    last_attempt_at: float = 0.0


class PendingAssignments:
    """Tracks the desired channel -> spool mapping until Klipper accepts it."""

    def __init__(self, clock: MonotonicClock = time.monotonic) -> None:
        self._clock = clock
        self._pending: dict[int, _PendingItem] = {}

    def update(self, channel: int, spool_id: int) -> None:
        """Queue (or refresh) the desired spool for ``channel``."""
        now = self._clock()
        existing = self._pending.get(channel)
        if existing and existing.spool_id == spool_id:
            existing.updated_at = now
            return

        self._pending[channel] = _PendingItem(spool_id=spool_id, updated_at=now)
        logger.info("Queued assignment: channel %s -> spool %s", channel, spool_id)

    def ready(self, retry_interval: float) -> list[tuple[int, int]]:
        """Channels whose last attempt is older than ``retry_interval``."""
        now = self._clock()
        return [
            (channel, item.spool_id)
            for channel, item in self._pending.items()
            if now - item.last_attempt_at >= retry_interval
        ]

    def mark_attempt(self, channel: int) -> None:
        item = self._pending.get(channel)
        if item is not None:
            item.last_attempt_at = self._clock()

    def mark_success(self, channel: int, spool_id: int) -> None:
        item = self._pending.get(channel)
        if item is not None and item.spool_id == spool_id:
            del self._pending[channel]
            logger.info(
                "Assignment applied: channel %s -> spool %s", channel, spool_id
            )

    def has_pending(self) -> bool:
        return bool(self._pending)
