#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Define variables
BASE_URL="https://raw.githubusercontent.com/BryanSmee/snapmaker-u1-rfidsync/refs/heads/main"
BASE_DIR="/home/lava/printer_data/config/extended"
KLIPPER_DIR="${BASE_DIR}/klipper"
MOONRAKER_DIR="${BASE_DIR}/moonraker"
USER_GROUP="lava:lava"

# Colors for output formatting
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}Starting Snapmaker U1 RFID Sync Installation...${NC}\n"

# 1. Create necessary directories
echo -e "Creating target directories..."
mkdir -p "${KLIPPER_DIR}"
mkdir -p "${MOONRAKER_DIR}"

# 2. Download and configure 01_spoolman_klipper.cfg
echo -e "Downloading 01_spoolman_klipper.cfg..."
curl -fsSL "${BASE_URL}/01_spoolman_klipper.cfg" -o "${KLIPPER_DIR}/01_spoolman_klipper.cfg"

# 3. Download and configure nfc_spool_reader.py
echo -e "Downloading nfc_spool_reader.py..."
curl -fsSL "${BASE_URL}/nfc_spool_reader.py" -o "${BASE_DIR}/nfc_spool_reader.py"
chmod +x "${BASE_DIR}/nfc_spool_reader.py"

# 4. Create variables.cfg for spool data persistence
echo -e "Setting up variables.cfg..."
touch "${BASE_DIR}/variables.cfg"
chown ${USER_GROUP} "${BASE_DIR}/variables.cfg"

# 5. Download 05_spoolman.cfg (Skip if exists)
if [ ! -f "${MOONRAKER_DIR}/05_spoolman.cfg" ]; then
    echo -e "Downloading 05_spoolman.cfg..."
    curl -fsSL "${BASE_URL}/05_spoolman.cfg" -o "${MOONRAKER_DIR}/05_spoolman.cfg"
else
    echo -e "${YELLOW}05_spoolman.cfg already exists. Skipping download to avoid overwriting your settings.${NC}"
fi

# 6. Download start_nfc_spool.sh
echo -e "Downloading start_nfc_spool.sh..."
curl -fsSL "${BASE_URL}/start_nfc_spool.sh" -o "${BASE_DIR}/start_nfc_spool.sh"
chmod +x "${BASE_DIR}/start_nfc_spool.sh"

echo -e "\n${GREEN}✔ File downloads and permissions setup complete!${NC}\n"

# Print Manual Instructions for the user
echo -e "${YELLOW}========================================================================${NC}"
echo -e "${YELLOW}                      MANUAL STEPS REQUIRED                             ${NC}"
echo -e "${YELLOW}========================================================================${NC}"

echo -e "1. Edit your URLs:"
echo -e "   - Open ${CYAN}${BASE_DIR}/nfc_spool_reader.py${NC} and update 'SPOOLMAN_API_BASE' to match your setup."
echo -e "   - If you just downloaded ${CYAN}${MOONRAKER_DIR}/05_spoolman.cfg${NC}, update the Spoolman URL inside to match your setup."

echo -e "\n2. Restart Klipper:"
echo -e "   - Go to the Fluidd UI -> 'System' tab and Restart the Klipper service."

echo -e "\n3. Update your Machine G-Code in your Slicer:"
echo -e "   - Click the pencil icon next to the printer name."
echo -e "   - Go to the 'Machine G-code' tab."
echo -e "   - In 'Machine start G-code' (scroll down ~80%), find ${CYAN}BED_MESH_CALIBRATE PROBE_COUNT${NC}."
echo -e "   - Add ${GREEN}START_SPOOLMAN_TRACKING${NC} directly below it."
echo -e "   - In 'Change filament G-code', delete the line saying: ${CYAN}\"USE_CHANNEL CHANNEL=\" + next_extruder + \"${NC} and the line immediately below it."
echo -e "   - Save the new machine profile and use it for your prints."

echo -e "\n4. Start the Service:"
echo -e "   Run this command to start the NFC reader script in the background:"
echo -e "   ${GREEN}sh ${BASE_DIR}/start_nfc_spool.sh &${NC}"

echo -e "\n5. Verify Operation:"
echo -e "   Check the logs using: ${CYAN}tail -f /home/lava/printer_data/logs/nfc_spool_reader.log${NC}"
echo -e "   In the Fluidd console, run ${GREEN}START_SPOOLMAN_TRACKING${NC} followed by ${GREEN}SHOW_SPOOL_STATE${NC} to confirm spools are loaded."
echo -e "${YELLOW}========================================================================${NC}\n"
