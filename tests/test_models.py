from rfidsync.models import OpenSpoolRecord, PendingScanEvent


def test_spool_id_valid():
    assert OpenSpoolRecord(0, {"spool_id": "42"}).spool_id == 42
    assert OpenSpoolRecord(1, {"spool_id": 7}).spool_id == 7


def test_spool_id_missing_or_invalid():
    assert OpenSpoolRecord(0, {}).spool_id is None
    assert OpenSpoolRecord(0, {"spool_id": ""}).spool_id is None
    assert OpenSpoolRecord(0, {"spool_id": None}).spool_id is None
    assert OpenSpoolRecord(0, {"spool_id": "abc"}).spool_id is None


def test_fingerprint_is_stable_and_distinct():
    a = OpenSpoolRecord(0, {"spool_id": 5, "extra": "x"})
    b = OpenSpoolRecord(0, {"spool_id": 5, "other": "y"})
    c = OpenSpoolRecord(1, {"spool_id": 5})
    assert a.fingerprint() == b.fingerprint()
    assert a.fingerprint() != c.fingerprint()


def test_pending_scan_event_expiry():
    event = PendingScanEvent(started_line_no=10, started_monotonic=100.0)
    assert not event.is_expired(15, 105.0, max_lines=120, max_age_seconds=10.0)
    assert event.is_expired(200, 105.0, max_lines=120, max_age_seconds=10.0)
    assert event.is_expired(15, 200.0, max_lines=120, max_age_seconds=10.0)
