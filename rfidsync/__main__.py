"""Console entrypoint: ``python -m rfidsync``."""

from __future__ import annotations

import logging

from .app import NFCSpoolReaderApp
from .config import Config


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    config = Config.from_env()
    configure_logging(config.log_level)
    logger = logging.getLogger("rfidsync")
    logger.info("Starting Remote NFC Spool Reader")
    logger.info("Moonraker: %s | Spoolman: %s", config.moonraker_base, config.spoolman_base)
    try:
        NFCSpoolReaderApp(config).run()
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
    finally:
        logger.info("Shutting down")


if __name__ == "__main__":
    main()
