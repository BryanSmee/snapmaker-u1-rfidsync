# Snapmaker U1 RFID Sync

Automatically track filament usage on a Snapmaker U1 by syncing scanned
OpenSpool NFC tags to [Spoolman](https://github.com/Donkie/Spoolman) — no
manual spool selection or QR scanning.

This runs entirely **remotely** as a Docker container. It talks to the printer
over the Klipper/Moonraker HTTP API: it watches the printer's `openrfid.log`,
resolves each scanned tag to a Spoolman spool, and tells Klipper which spool is
loaded on each channel. On boot it also installs the required Klipper/Moonraker
config snippets onto the printer for you.

## How it works

Each toolhead maps to a fixed channel (`extruder` → 0 … `extruder3` → 3). Each
channel stores a spool ID in a persistent Klipper variable, so the active spool
follows the selected tool automatically and survives restarts.

```
NFC scan → openrfid.log → (this container) → Moonraker → Klipper → Spoolman
```

1. The container polls `openrfid.log` through the Moonraker file API.
2. When a tag is scanned, it parses the OpenSpool JSON payload and the slot it
   was read on.
3. It validates the spool ID against Spoolman.
4. It calls `SET_CHANNEL_SPOOL` via Moonraker, which Klipper persists.

## Requirements

- [Extended firmware](https://github.com/paxx12/SnapmakerU1-Extended-Firmware)
- A reachable [Spoolman](https://github.com/Donkie/Spoolman) instance.
- OpenSpool NFC tags (e.g. written with
  [spoolpainter](https://play.google.com/store/apps/details?id=com.spoolpainter.app)).
  Any OEM tags must be physically removed — this only works with the OpenSpool
  protocol.
- Docker (and Docker Compose) on a host that can reach the printer's Moonraker
  port (`7125`) and your Spoolman instance.

## Running

### Docker Compose (recommended)

Edit the environment in [`compose.yaml`](./compose.yaml) to point at your
printer and Spoolman, then:

```bash
docker compose up -d
```

The image is published to GHCR, so you can also just pull it:

```bash
docker pull ghcr.io/bryansmee/snapmaker-u1-rfidsync:latest
```

### docker run

```bash
docker run -d --restart=always \
  -e MOONRAKER_URL=http://<printer-ip>:7125 \
  -e SPOOLMAN_URL=http://<spoolman-ip>:7912 \
  ghcr.io/bryansmee/snapmaker-u1-rfidsync:latest
```

## Configuration

All configuration is via environment variables.

| Variable | Default | Description |
| --- | --- | --- |
| `MOONRAKER_URL` | `http://localhost:7125` | Base URL of the printer's Moonraker. |
| `SPOOLMAN_URL` | `http://spoolman:7912` | Base URL of Spoolman (no `/api`). |
| `MOONRAKER_API_KEY` | _(none)_ | Sent as `X-Api-Key` if Moonraker auth is enabled. |
| `SPOOLMAN_SYNC_RATE` | `5` | `sync_rate` written into the Moonraker spoolman config. |
| `POLL_INTERVAL` | `3.0` | Seconds between log polls. |
| `START_AT_END` | `true` | Ignore pre-existing log lines on startup. |
| `LOG_LEVEL` | `INFO` | Python log level. |
| `LOG_RAW_LINES` | `false` | Log every raw log line (very verbose). |
| `INSTALL_CONFIGS` | `true` | Install the cfg snippets on boot. |
| `RESTART_KLIPPER_AFTER_INSTALL` | `false` | Restart Klipper if a snippet changed. |
| `REQUEST_TIMEOUT` | `30` | HTTP timeout (seconds). |
| `DEDUP_SECONDS` | `10.0` | Suppress identical scans within this window. |
| `EVENT_MAX_LINES` / `EVENT_MAX_AGE_SECONDS` | `120` / `10.0` | How long a payload waits for its slot line. |
| `ASSIGNMENT_RETRY_INTERVAL` | `5.0` | Retry interval for assignments Klipper rejected. |

## Config snippets installed on boot

On startup (unless `INSTALL_CONFIGS=false`) the container uses the Moonraker
file API to keep these in sync with the versions shipped in the image:

| File | Destination (Moonraker `config` root) |
| --- | --- |
| `01_spoolman_klipper.cfg` | `extended/klipper/01_spoolman_klipper.cfg` |
| `05_spoolman.cfg.tmpl` | `extended/moonraker/05_spoolman.cfg` (rendered from env vars) |
| `variables.cfg` | `extended/variables.cfg` (created empty **only if missing**) |

Managed snippets are deleted and rewritten when their content differs.
`variables.cfg` holds persistent spool state and is never overwritten.

Because these change Klipper config, a Klipper restart is needed for them to
take effect. This is **opt-in** via `RESTART_KLIPPER_AFTER_INSTALL=true` (only
restarts when something actually changed) so the container never interrupts a
running print unexpectedly. Otherwise, restart Klipper from the Fluidd
**System** tab after the first run.

## One-time slicer change

The container handles everything on the printer side, but your slicer's machine
G-code must stop reassigning channels itself:

1. Edit the printer profile → **Machine G-code**.
2. In **Machine start G-code**, find `BED_MESH_CALIBRATE PROBE_COUNT` and add
   `START_SPOOLMAN_TRACKING` directly below it.
3. In **Change filament G-code**, delete the line
   `"USE_CHANNEL CHANNEL=" + next_extruder + "` and the line below it.
4. Save the profile and use it for your prints.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest        # tests
mypy rfidsync # type checking
```

The application lives in the [`rfidsync`](./rfidsync) package:

- `config.py` — env-var configuration
- `moonraker.py` / `spoolman.py` — HTTP clients
- `watcher.py` — parses scans from `openrfid.log`
- `installer.py` — boot-time cfg installation
- `assignments.py` — dedup + retrying channel assignments
- `app.py` — wiring and the poll loop

> The original gcode blocks and parsing logic were AI-assisted; bug reports
> welcome.
