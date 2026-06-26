import requests_mock

from rfidsync.moonraker import MoonrakerClient

BASE = "http://printer:7125"


def make_client():
    return MoonrakerClient(BASE, timeout=5)


def test_set_channel_spool_success():
    with requests_mock.Mocker() as m:
        m.post(f"{BASE}/printer/gcode/script", json={"result": "ok"})
        assert make_client().set_channel_spool(1, 42) is True
        assert m.last_request.json() == {
            "script": "SET_CHANNEL_SPOOL CHANNEL=1 ID=42"
        }


def test_set_channel_spool_failure():
    with requests_mock.Mocker() as m:
        m.post(f"{BASE}/printer/gcode/script", status_code=500)
        assert make_client().set_channel_spool(1, 42) is False


def test_list_and_exists():
    with requests_mock.Mocker() as m:
        m.get(
            f"{BASE}/server/files/list",
            json={"result": [{"path": "extended/variables.cfg"}]},
        )
        client = make_client()
        assert client.file_exists("config", "extended/variables.cfg") is True
        assert client.file_exists("config", "missing.cfg") is False


def test_read_file_missing_returns_none():
    with requests_mock.Mocker() as m:
        m.get(f"{BASE}/server/files/config/x.cfg", status_code=404)
        assert make_client().read_file("config", "x.cfg") is None


def test_read_file_returns_text():
    with requests_mock.Mocker() as m:
        m.get(f"{BASE}/server/files/config/x.cfg", text="hello")
        assert make_client().read_file("config", "x.cfg") == "hello"


def test_delete_file_ignores_404():
    with requests_mock.Mocker() as m:
        m.delete(f"{BASE}/server/files/config/x.cfg", status_code=404)
        make_client().delete_file("config", "x.cfg")  # no raise


def test_upload_file_sends_root_path_and_filename():
    with requests_mock.Mocker() as m:
        m.post(f"{BASE}/server/files/upload", json={"result": "ok"})
        make_client().upload_file(
            "config", "extended/klipper/01.cfg", "content"
        )
        body = m.last_request.text
        assert 'name="root"' in body
        assert "config" in body
        assert "extended/klipper" in body
        assert "01.cfg" in body


def test_api_key_header_is_set():
    client = MoonrakerClient(BASE, api_key="secret")
    assert client.session.headers["X-Api-Key"] == "secret"
