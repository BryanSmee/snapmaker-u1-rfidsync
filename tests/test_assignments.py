from rfidsync.assignments import Deduper, PendingAssignments


class FakeClock:
    def __init__(self) -> None:
        # Start non-zero to mirror time.monotonic(), which never returns 0.
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_deduper_suppresses_within_ttl():
    clock = FakeClock()
    dedup = Deduper(ttl_seconds=10.0, clock=clock)
    assert dedup.is_duplicate("a") is False
    assert dedup.is_duplicate("a") is True
    clock.advance(11.0)
    assert dedup.is_duplicate("a") is False


def test_pending_queue_and_success():
    clock = FakeClock()
    pending = PendingAssignments(clock=clock)
    assert pending.has_pending() is False

    pending.update(0, 5)
    assert pending.has_pending() is True
    assert pending.ready(retry_interval=5.0) == [(0, 5)]

    pending.mark_attempt(0)
    # Too soon to retry.
    assert pending.ready(retry_interval=5.0) == []
    clock.advance(6.0)
    assert pending.ready(retry_interval=5.0) == [(0, 5)]

    pending.mark_success(0, 5)
    assert pending.has_pending() is False


def test_update_replaces_spool_for_channel():
    clock = FakeClock()
    pending = PendingAssignments(clock=clock)
    pending.update(0, 5)
    pending.update(0, 9)
    assert pending.ready(retry_interval=0.0) == [(0, 9)]


def test_mark_success_ignored_if_spool_changed():
    pending = PendingAssignments(clock=FakeClock())
    pending.update(0, 5)
    pending.mark_success(0, 99)  # stale success
    assert pending.has_pending() is True
