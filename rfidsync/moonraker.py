"""Thin Moonraker HTTP client covering the endpoints this app needs."""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


class MoonrakerClient:
    """Wraps the subset of the Moonraker API used for sync and installation."""

    def __init__(
        self,
        base_url: str,
        timeout: int = 30,
        api_key: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        if api_key:
            self.session.headers["X-Api-Key"] = api_key

    # --- G-code -----------------------------------------------------------

    def set_channel_spool(self, channel: int, spool_id: int) -> bool:
        """Run ``SET_CHANNEL_SPOOL``; return True if Moonraker accepted it."""
        script = f"SET_CHANNEL_SPOOL CHANNEL={channel} ID={spool_id}"
        try:
            resp = self.session.post(
                f"{self.base_url}/printer/gcode/script",
                json={"script": script},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            logger.info("Moonraker accepted gcode: %s", script)
            return True
        except requests.exceptions.RequestException:
            logger.exception("HTTP error sending gcode: %s", script)
            return False

    # --- File manager -----------------------------------------------------

    def list_files(self, root: str) -> list[dict[str, Any]]:
        """Return the file listing for a Moonraker root (e.g. ``config``)."""
        resp = self.session.get(
            f"{self.base_url}/server/files/list",
            params={"root": root},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        result: list[dict[str, Any]] = resp.json().get("result", [])
        return result

    def file_exists(self, root: str, path: str) -> bool:
        """Whether ``path`` (relative to ``root``) exists in the file manager."""
        return any(item.get("path") == path for item in self.list_files(root))

    def read_file(self, root: str, path: str) -> str | None:
        """Return the text content of a file, or ``None`` if it is missing."""
        resp = self.session.get(
            f"{self.base_url}/server/files/{root}/{path}",
            timeout=self.timeout,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.text

    def delete_file(self, root: str, path: str) -> None:
        """Delete a file; a 404 is treated as already-deleted."""
        resp = self.session.delete(
            f"{self.base_url}/server/files/{root}/{path}",
            timeout=self.timeout,
        )
        if resp.status_code == 404:
            return
        resp.raise_for_status()

    def upload_file(self, root: str, path: str, content: str) -> None:
        """Upload ``content`` to ``root/path`` via the file-manager endpoint.

        ``path`` is the full destination path relative to the root, including
        the filename (e.g. ``extended/klipper/01_spoolman_klipper.cfg``).
        """
        directory, _, filename = path.rpartition("/")
        data = {"root": root}
        if directory:
            data["path"] = directory
        resp = self.session.post(
            f"{self.base_url}/server/files/upload",
            data=data,
            files={"file": (filename, content.encode("utf-8"), "text/plain")},
            timeout=self.timeout,
        )
        resp.raise_for_status()

    # --- Service control --------------------------------------------------

    def restart_klipper(self) -> None:
        """Ask Moonraker to restart the Klipper service."""
        resp = self.session.post(
            f"{self.base_url}/printer/restart",
            timeout=self.timeout,
        )
        resp.raise_for_status()
