"""Remote NFC/OpenSpool to Spoolman sync for the Snapmaker U1.

This package watches the printer's ``openrfid.log`` through the Moonraker
file API, resolves scanned OpenSpool tags to Spoolman spool IDs and pushes
channel assignments back to Klipper. It also installs the required Klipper
and Moonraker config snippets on boot.
"""

__all__ = ["__version__"]

__version__ = "1.0.0"
