from rfidsync.watcher import OpenRFIDLogWatcher


class FakeMoonraker:
    """Stands in for MoonrakerClient, serving canned log content/metadata."""

    def __init__(self) -> None:
        self.text = ""
        self.modified = 1.0
        self.size = 0

    def set_log(self, text: str) -> None:
        self.text = text
        self.modified += 1.0
        self.size = len(text)

    def list_files(self, root: str):
        return [{"path": "openrfid.log", "modified": self.modified, "size": self.size}]

    def read_file(self, root: str, path: str):
        return self.text


PAYLOAD = 'OpenSpool JSON payload: {"spool_id": 42}'
SLOT = "tag detected on reader slot_1_reader"


def make_watcher(moonraker, **kwargs):
    return OpenRFIDLogWatcher(moonraker, start_at_end=False, **kwargs)


def test_parses_payload_then_slot():
    fake = FakeMoonraker()
    fake.set_log(f"{PAYLOAD}\n{SLOT}\n")
    watcher = make_watcher(fake)

    records = watcher.poll()
    assert len(records) == 1
    assert records[0].channel == 1
    assert records[0].spool_id == 42


def test_slot_without_payload_is_ignored():
    fake = FakeMoonraker()
    fake.set_log(f"{SLOT}\n")
    assert make_watcher(fake).poll() == []


def test_start_at_end_skips_existing_lines():
    fake = FakeMoonraker()
    fake.set_log(f"{PAYLOAD}\n{SLOT}\n")
    watcher = OpenRFIDLogWatcher(fake, start_at_end=True)
    assert watcher.poll() == []

    fake.set_log(f"{PAYLOAD}\n{SLOT}\n{PAYLOAD}\n{SLOT}\n")
    records = watcher.poll()
    assert len(records) == 1


def test_no_redownload_when_metadata_unchanged():
    fake = FakeMoonraker()
    fake.set_log(f"{PAYLOAD}\n{SLOT}\n")
    watcher = make_watcher(fake)
    assert len(watcher.poll()) == 1

    # No new write -> metadata unchanged -> nothing returned.
    assert watcher.poll() == []


def test_log_rotation_resets_cursor():
    fake = FakeMoonraker()
    fake.set_log(f"line1\nline2\n{PAYLOAD}\n{SLOT}\n")
    watcher = make_watcher(fake)
    assert len(watcher.poll()) == 1

    # Log shrinks (rotated) and contains a fresh scan.
    fake.set_log(f"{PAYLOAD}\n{SLOT}\n")
    records = watcher.poll()
    assert len(records) == 1


def test_event_expires_after_max_lines():
    fake = FakeMoonraker()
    filler = "\n".join("noise" for _ in range(5))
    fake.set_log(f"{PAYLOAD}\n{filler}\n{SLOT}\n")
    watcher = make_watcher(fake, event_max_lines=2)
    assert watcher.poll() == []


def test_malformed_json_is_skipped():
    fake = FakeMoonraker()
    fake.set_log(f"OpenSpool JSON payload: {{not json}}\n{SLOT}\n")
    assert make_watcher(fake).poll() == []
