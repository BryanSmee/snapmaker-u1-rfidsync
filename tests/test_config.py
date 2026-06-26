from rfidsync.config import Config


def test_defaults_when_env_empty(monkeypatch):
    for var in [
        "MOONRAKER_URL",
        "SPOOLMAN_URL",
        "POLL_INTERVAL",
        "INSTALL_CONFIGS",
    ]:
        monkeypatch.delenv(var, raising=False)
    cfg = Config.from_env()
    assert cfg.moonraker_url == "http://localhost:7125"
    assert cfg.spoolman_url == "http://spoolman:7912"
    assert cfg.poll_interval == 3.0
    assert cfg.install_configs is True


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("MOONRAKER_URL", "http://printer:7125/")
    monkeypatch.setenv("SPOOLMAN_URL", "http://spool:7912/")
    monkeypatch.setenv("POLL_INTERVAL", "1.5")
    monkeypatch.setenv("START_AT_END", "false")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("INSTALL_CONFIGS", "0")
    cfg = Config.from_env()
    assert cfg.poll_interval == 1.5
    assert cfg.start_at_end is False
    assert cfg.log_level == "DEBUG"
    assert cfg.install_configs is False


def test_derived_urls(monkeypatch):
    monkeypatch.setenv("MOONRAKER_URL", "http://printer:7125/")
    monkeypatch.setenv("SPOOLMAN_URL", "http://spool:7912/")
    cfg = Config.from_env()
    assert cfg.moonraker_base == "http://printer:7125"
    assert cfg.spoolman_base == "http://spool:7912"
    assert cfg.spoolman_api_base == "http://spool:7912/api/v1"
    assert cfg.gcode_url == "http://printer:7125/printer/gcode/script"


def test_invalid_numbers_fall_back_to_default(monkeypatch):
    monkeypatch.setenv("POLL_INTERVAL", "not-a-number")
    monkeypatch.setenv("REQUEST_TIMEOUT", "abc")
    cfg = Config.from_env()
    assert cfg.poll_interval == 3.0
    assert cfg.request_timeout == 30


def test_bool_parsing(monkeypatch):
    for value, expected in [("yes", True), ("ON", True), ("0", False), ("no", False)]:
        monkeypatch.setenv("LOG_RAW_LINES", value)
        assert Config.from_env().log_raw_lines is expected
