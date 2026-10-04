#!/usr/bin/env python3
"""Entrypoint for the Home Assistant Muse Gadget Add-on.

Manages token loading from add-on options, persistent state in /data,
Bluetooth LE pairing, and launches the musegadget daemon with Home Assistant tools.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("musegadget.entrypoint")

OPTIONS_FILE = Path("/data/options.json")
STATE_DIR = Path("/data")
PAIRING_FILE = STATE_DIR / "pairing.json"


def load_options() -> dict:
    if OPTIONS_FILE.exists():
        try:
            with open(OPTIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            log.warning("Could not read /data/options.json: %s", exc)
    return {}


def main() -> int:
    log.info("Starting Home Assistant Muse Gadget Add-on...")

    options = load_options()
    sdk_token = options.get("sdk_token", "").strip() or os.environ.get("MUSEGADGET_SDK_TOKEN", "").strip()
    ha_url = options.get("ha_url", "").strip() or os.environ.get("HA_URL", "http://supervisor/core/api")
    ha_token = options.get("ha_token", "").strip() or os.environ.get("HA_TOKEN", "")

    # Validate SDK Token
    while not sdk_token:
        log.error("==================================================================")
        log.error(" [CONFIGURATION REQUIRED] No 'sdk_token' specified in Add-on config!")
        log.error(" 1. Visit: https://gadgets.muse.ai/settings/sdk-tokens")
        log.error(" 2. Generate or copy your SDK Token (starts with 'mgst_')")
        log.error(" 3. Paste it into Home Assistant -> Settings -> Add-ons -> Muse Gadget -> Configuration")
        log.error(" 4. Click 'Save' and restart this add-on.")
        log.error("==================================================================")
        time.sleep(30)
        options = load_options()
        sdk_token = options.get("sdk_token", "").strip()

    os.environ["MUSEGADGET_STATE_DIR"] = str(STATE_DIR)
    os.environ["MUSEGADGET_SDK_TOKEN"] = sdk_token
    os.environ["MUSEGADGET_RUN_AS"] = "muse"
    os.environ["HA_URL"] = ha_url
    if ha_token:
        os.environ["HA_TOKEN"] = ha_token

    # Install custom Home Assistant tools into COMMAND_SPECS & Executor
    try:
        from ha_bridge import install_ha_tools
        install_ha_tools()
    except Exception as exc:
        log.exception("Failed to install Home Assistant tools: %s", exc)

    # Check for direct pairing credentials injection from add-on options
    pairing_json_opt = options.get("pairing_json", "").strip()
    if pairing_json_opt and not PAIRING_FILE.exists():
        try:
            parsed = json.loads(pairing_json_opt)
            if "access_token" in parsed and "refresh_token" in parsed:
                with open(PAIRING_FILE, "w", encoding="utf-8") as f:
                    json.dump(parsed, f, indent=2)
                log.info("==================================================================")
                log.info(" [CREDENTIALS IMPORTED] Successfully loaded pairing.json from Add-on Config!")
                log.info(" Skipping Bluetooth LE setup.")
                log.info("==================================================================")
        except Exception as exc:
            log.warning("Could not parse 'pairing_json' option: %s", exc)

    # Check pairing state
    if not PAIRING_FILE.exists():
        log.info("------------------------------------------------------------------")
        log.info(" [PAIRING MODE ACTIVATED]")
        log.info(" Device is not paired with your Meta Muse account.")
        log.info(" Keeping Bluetooth LE pairing open for 10 minutes...")
        log.info("")
        log.info(" Action required:")
        log.info("   1. Open the Meta Muse mobile app on your smartphone.")
        log.info("   2. Go to Settings > Devices and turn on Developer mode.")
        log.info("   3. Tap '+' (Add Device) in the top-right corner.")
        log.info("   4. Select your device (it will appear as 'MuseGadgetXXXXXX').")
        log.info("   5. Choose your local Wi-Fi when prompted to finalize pairing.")
        log.info("------------------------------------------------------------------")

        # Apply BLE stability patches for BlueZ adapter & connection handling
        try:
            from ble_patch import apply_ble_patches
            apply_ble_patches()
        except Exception as exc:
            log.exception("Failed to apply BLE stability patches: %s", exc)

        import argparse
        from musegadget.cli import cmd_pair

        pair_args = argparse.Namespace(
            command="pair",
            timeout=600,
            force=False,
            verbose=True,
        )
        rc = cmd_pair(pair_args)
        if rc != 0:
            log.warning("Pairing process returned code %d", rc)

    if not PAIRING_FILE.exists():
        log.warning("Pairing was not completed within the timeout window.")
        log.warning("Restarting pairing window...")
        return 1

    log.info("Pairing credentials verified. Connecting to Muse cloud VM...")

    # Run service daemon
    from musegadget.cli import cmd_run
    import argparse
    run_args = argparse.Namespace(
        run_as="muse",
        command="run",
    )
    return cmd_run(run_args)


if __name__ == "__main__":
    sys.exit(main())
