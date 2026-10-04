# Changelog

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
