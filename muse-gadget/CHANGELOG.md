# Changelog

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
