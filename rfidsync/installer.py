"""Installs the Klipper/Moonraker config snippets via the Moonraker file API.

On boot the managed snippets are (re)written so the printer always runs the
version shipped in this image. ``variables.cfg`` holds persistent spool state
and is therefore only created when missing - never overwritten.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .moonraker import MoonrakerClient

logger = logging.getLogger(__name__)

DEFAULT_CFG_DIR = Path(__file__).resolve().parent.parent / "cfg"

# Moonraker root used for both Klipper and Moonraker config snippets.
CONFIG_ROOT = "config"

# Persistent spool state; created empty when absent, never overwritten.
VARIABLES_PATH = "extended/variables.cfg"


@dataclass(frozen=True)
class ManagedConfig:
    """A bundled snippet and where it should land on the printer."""

    source: str  # filename inside the cfg directory
    dest: str  # path relative to the Moonraker ``config`` root
    template: bool = False  # render with str.format using config values


MANAGED_CONFIGS: tuple[ManagedConfig, ...] = (
    ManagedConfig(
        source="01_spoolman_klipper.cfg",
        dest="extended/klipper/01_spoolman_klipper.cfg",
    ),
    ManagedConfig(
        source="05_spoolman.cfg.tmpl",
        dest="extended/moonraker/05_spoolman.cfg",
        template=True,
    ),
)


class ConfigInstaller:
    """Synchronises the managed config snippets onto the printer."""

    def __init__(
        self,
        moonraker: MoonrakerClient,
        config: Config,
        cfg_dir: Path | None = None,
    ) -> None:
        self.moonraker = moonraker
        self.config = config
        env_dir = os.getenv("CFG_DIR")
        self.cfg_dir = cfg_dir or (Path(env_dir) if env_dir else DEFAULT_CFG_DIR)

    def _render(self, managed: ManagedConfig) -> str:
        raw = (self.cfg_dir / managed.source).read_text(encoding="utf-8")
        if not managed.template:
            return raw
        return raw.format(
            spoolman_server=self.config.spoolman_base,
            spoolman_sync_rate=self.config.spoolman_sync_rate,
        )

    def _install_one(self, managed: ManagedConfig) -> bool:
        """Delete and rewrite a managed file. Returns True if content changed."""
        desired = self._render(managed)
        current = self.moonraker.read_file(CONFIG_ROOT, managed.dest)

        if current == desired:
            logger.info("%s already up to date", managed.dest)
            return False

        if current is not None:
            logger.info("Replacing existing %s", managed.dest)
            self.moonraker.delete_file(CONFIG_ROOT, managed.dest)
        else:
            logger.info("Creating %s", managed.dest)

        self.moonraker.upload_file(CONFIG_ROOT, managed.dest, desired)
        return True

    def _ensure_variables_file(self) -> None:
        """Create an empty ``variables.cfg`` only if it does not already exist."""
        if self.moonraker.file_exists(CONFIG_ROOT, VARIABLES_PATH):
            logger.info("%s already present, leaving it untouched", VARIABLES_PATH)
            return
        logger.info("Creating empty %s", VARIABLES_PATH)
        self.moonraker.upload_file(CONFIG_ROOT, VARIABLES_PATH, "")

    def install(self) -> bool:
        """Install all managed configs. Returns True if anything changed."""
        logger.info("Installing managed config snippets via Moonraker")
        changed = False
        for managed in MANAGED_CONFIGS:
            changed |= self._install_one(managed)
        self._ensure_variables_file()

        if changed and self.config.restart_klipper_after_install:
            logger.info("Config changed - restarting Klipper")
            self.moonraker.restart_klipper()
        return changed
