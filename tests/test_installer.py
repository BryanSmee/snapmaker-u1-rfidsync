from rfidsync.config import Config
from rfidsync.installer import ConfigInstaller


class FakeMoonraker:
    """In-memory stand-in for the Moonraker file API."""

    def __init__(self, files: dict[str, str] | None = None) -> None:
        # keyed by "root/path"
        self.files: dict[str, str] = files or {}
        self.deleted: list[str] = []
        self.uploaded: list[str] = []
        self.restarted = False

    def _key(self, root: str, path: str) -> str:
        return f"{root}/{path}"

    def list_files(self, root: str):
        return [
            {"path": key.split("/", 1)[1]}
            for key in self.files
            if key.startswith(f"{root}/")
        ]

    def file_exists(self, root: str, path: str) -> bool:
        return self._key(root, path) in self.files

    def read_file(self, root: str, path: str):
        return self.files.get(self._key(root, path))

    def delete_file(self, root: str, path: str) -> None:
        key = self._key(root, path)
        self.deleted.append(key)
        self.files.pop(key, None)

    def upload_file(self, root: str, path: str, content: str) -> None:
        key = self._key(root, path)
        self.uploaded.append(key)
        self.files[key] = content

    def restart_klipper(self) -> None:
        self.restarted = True


def make_config(**kwargs) -> Config:
    base = dict(spoolman_url="http://spool:7912", spoolman_sync_rate=5)
    base.update(kwargs)
    return Config(**base)


def test_fresh_install_uploads_everything():
    fake = FakeMoonraker()
    changed = ConfigInstaller(fake, make_config()).install()

    assert changed is True
    assert "config/extended/klipper/01_spoolman_klipper.cfg" in fake.uploaded
    assert "config/extended/moonraker/05_spoolman.cfg" in fake.uploaded
    assert "config/extended/variables.cfg" in fake.uploaded


def test_spoolman_template_is_rendered():
    fake = FakeMoonraker()
    ConfigInstaller(fake, make_config()).install()
    rendered = fake.files["config/extended/moonraker/05_spoolman.cfg"]
    assert "server: http://spool:7912" in rendered
    assert "sync_rate: 5" in rendered
    assert "{spoolman_server}" not in rendered


def test_existing_variables_file_is_not_overwritten():
    fake = FakeMoonraker({"config/extended/variables.cfg": "spool_ch0 = 7"})
    ConfigInstaller(fake, make_config()).install()
    # variables.cfg must keep its persisted state.
    assert fake.files["config/extended/variables.cfg"] == "spool_ch0 = 7"
    assert "config/extended/variables.cfg" not in fake.uploaded


def test_outdated_config_is_deleted_then_rewritten():
    fake = FakeMoonraker(
        {"config/extended/klipper/01_spoolman_klipper.cfg": "stale content"}
    )
    changed = ConfigInstaller(fake, make_config()).install()
    assert changed is True
    assert "config/extended/klipper/01_spoolman_klipper.cfg" in fake.deleted
    assert "config/extended/klipper/01_spoolman_klipper.cfg" in fake.uploaded


def test_no_change_when_already_current():
    fake = FakeMoonraker()
    ConfigInstaller(fake, make_config()).install()
    fake.deleted.clear()
    fake.uploaded.clear()

    changed = ConfigInstaller(fake, make_config()).install()
    assert changed is False
    assert fake.uploaded == []
    assert fake.deleted == []


def test_restart_only_when_changed_and_enabled():
    fake = FakeMoonraker()
    ConfigInstaller(fake, make_config(restart_klipper_after_install=True)).install()
    assert fake.restarted is True

    # Second run: nothing changed, so no restart.
    fake.restarted = False
    ConfigInstaller(fake, make_config(restart_klipper_after_install=True)).install()
    assert fake.restarted is False
