"""Minimal Spoolman REST client."""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)


class SpoolmanClient:
    """Looks up spools in Spoolman to validate scanned IDs before applying them."""

    def __init__(
        self,
        base_url: str,
        timeout: int = 30,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()

    def spool_exists(self, spool_id: int) -> bool:
        """Return whether a spool with ``spool_id`` exists in Spoolman."""
        url = f"{self.base_url}/spool/{spool_id}"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                return True
            logger.warning(
                "Spool lookup failed: spool_id=%s status=%s", spool_id, resp.status_code
            )
            return False
        except requests.exceptions.RequestException:
            logger.exception("Error checking spool_id=%s at %s", spool_id, url)
            return False
