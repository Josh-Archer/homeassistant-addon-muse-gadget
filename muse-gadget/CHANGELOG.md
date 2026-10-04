# Changelog

## 1.1.0

- **Area & Room Intelligence**:
  - Added `homeassistant.list_areas`: Lists all rooms/areas in Home Assistant with area IDs, friendly names, and entity counts.
  - Added `homeassistant.get_area_devices`: Returns all entities in a room, their domains, device classes, and current states.
  - Room-level service targeting: `homeassistant.call_service` now supports `area_id` and `target: {"area_id": ...}` for commanding entire rooms (e.g. "turn off the living room lights").
- **Smart Entity Summaries & Pagination (Large Homes)**:
  - Added `area` filter to `homeassistant.list_states`.
  - Added pagination controls (`limit` 1-100, `offset`, `total`, `has_more`) to `homeassistant.list_states` to safely handle installations with 500+ entities without exceeding the 96 KiB Noise frame limit.
- **Proactive Notifications (`notify.muse`)**:
  - Added built-in lightweight async HTTP webhook on port 8099 (`POST /notify` and `GET /health`), allowing Home Assistant automations and scripts to push messages directly to your Meta Muse chat.
  - Added `homeassistant.notify_muse` tool for conversational notifications.
  - Added `muse-notify` CLI helper script inside the add-on container.
  - Added `ha-ctl areas` and `ha-ctl notify` helper commands.
- **Device Energy & Power Telemetry**:
  - Added `homeassistant.get_energy`: Queries Home Assistant Energy Dashboard and power/solar/battery telemetry.
- **Enriched Welcome Announcement**:
  - The automatic connection announcement now includes room counts in addition to total entity and domain counts.

## 1.0.4

- Added Automatic Meta Muse Chat Welcome Announcement: upon connecting and registering, the add-on sends an introductory message to your Meta Muse chat with your entity counts and capabilities, priming Muse's LLM context so it immediately knows how to control your smart home.
- Made Home Assistant URL and token evaluation dynamic per API request to prevent empty token caching.

## 1.0.3

- Added BlueZ `AutoPairAgent` (`org.bluez.Agent1` with `NoInputNoOutput` capability) to automatically authorize and confirm iOS system Bluetooth pairing requests ("Pair with MuseGadget").
- Prevents BlueZ connection teardowns when the user taps "Pair" on the iOS Bluetooth pairing dialog.
- Clean Agent registration and teardown on BlueZ D-Bus manager.

## 1.0.2

- Added Step-by-Step Pairing HUD with real-time stage logging and human-readable progress markers.
- Added Connection Forensics: logs connection duration, last active stage, and precise drop diagnostics (e.g. Home Assistant Bluetooth scanner collision vs signal drops).
- Added Direct Pairing Import: supports pasting `pairing.json` into Add-on Configuration as a bulletproof alternative to BLE pairing.
- Fixed BlueZ lifecycle runner: keeps Pairable, Discoverable, and Powered flags active without upstream overrides.
- Added Reconnection Watcher: logs 60s grace period countdown and seamless resumption on phone reconnect.
- Enhanced BlueZ Adapter status and MTU negotiation reporting.

## 1.0.1

- Fixed BLE connection dropping on iOS and Android during pairing sheet display.
- Enabled Pairable and Discoverable on BlueZ adapter to satisfy iOS CoreBluetooth SMP requirements.
- Automatically marks connected phones as Trusted in BlueZ to prevent connection teardowns.
- Clamped ATT MTU to 256 bytes to prevent attribute length exceptions.
- Added 60-second reconnection grace period so temporary BLE disconnects don't wipe confirmed pairing sessions.
- Paced BLE packet notifications to prevent controller buffer drops.

## 1.0.0

- Initial release of the Home Assistant Muse Gadget Add-on.
- Integrated Meta Muse Gadget SDK (Linux) with Bluetooth LE pairing support.
- Added native Home Assistant tool bridge for `homeassistant.call_service`, `homeassistant.get_state`, `homeassistant.list_states`, and `homeassistant.render_template`.
- Added automatic Supervisor token authentication.
