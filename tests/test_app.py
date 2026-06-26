from rfidsync.app import NFCSpoolReaderApp
from rfidsync.config import Config
from rfidsync.models import OpenSpoolRecord


def make_app() -> NFCSpoolReaderApp:
    return NFCSpoolReaderApp(Config())


def test_handle_record_queues_valid_scan(monkeypatch):
    app = make_app()
    monkeypatch.setattr(app.spoolman, "spool_exists", lambda spool_id: True)

    app.handle_record(OpenSpoolRecord(0, {"spool_id": 42}))
    assert app.pending_assignments.ready(retry_interval=0.0) == [(0, 42)]


def test_handle_record_skips_unknown_spool(monkeypatch):
    app = make_app()
    monkeypatch.setattr(app.spoolman, "spool_exists", lambda spool_id: False)

    app.handle_record(OpenSpoolRecord(0, {"spool_id": 42}))
    assert app.pending_assignments.has_pending() is False


def test_handle_record_skips_missing_spool_id(monkeypatch):
    app = make_app()
    called = []
    monkeypatch.setattr(
        app.spoolman, "spool_exists", lambda spool_id: called.append(spool_id) or True
    )
    app.handle_record(OpenSpoolRecord(0, {}))
    assert app.pending_assignments.has_pending() is False
    assert called == []  # Spoolman never queried for an invalid scan


def test_handle_record_dedups(monkeypatch):
    app = make_app()
    exists_calls = []
    monkeypatch.setattr(
        app.spoolman,
        "spool_exists",
        lambda spool_id: exists_calls.append(spool_id) or True,
    )
    app.handle_record(OpenSpoolRecord(0, {"spool_id": 42}))
    app.handle_record(OpenSpoolRecord(0, {"spool_id": 42}))
    assert exists_calls == [42]  # second identical scan suppressed


def test_flush_applies_and_clears_on_success(monkeypatch):
    app = make_app()
    sent = []
    monkeypatch.setattr(app.spoolman, "spool_exists", lambda spool_id: True)
    monkeypatch.setattr(
        app.moonraker,
        "set_channel_spool",
        lambda channel, spool_id: sent.append((channel, spool_id)) or True,
    )
    app.handle_record(OpenSpoolRecord(2, {"spool_id": 7}))
    app.flush_pending_assignments()
    assert sent == [(2, 7)]
    assert app.pending_assignments.has_pending() is False


def test_flush_keeps_pending_on_failure(monkeypatch):
    app = make_app()
    monkeypatch.setattr(app.spoolman, "spool_exists", lambda spool_id: True)
    monkeypatch.setattr(
        app.moonraker, "set_channel_spool", lambda channel, spool_id: False
    )
    app.handle_record(OpenSpoolRecord(2, {"spool_id": 7}))
    app.flush_pending_assignments()
    assert app.pending_assignments.has_pending() is True
