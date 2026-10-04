# Project Roadmap: Home Assistant Muse Gadget Bridge

This roadmap outlines the planned development, features, and community goals for the **Home Assistant Muse Gadget Add-on** (`homeassistant-addon-muse-gadget`), bridging Meta's personal AI agent (**Meta Muse**) with Home Assistant smart homes.

---

## 🚀 Vision
To make Meta Muse the most capable, natural, and seamless personal AI assistant for smart homes by pairing Meta's state-of-the-art conversational AI models with Home Assistant's local execution, deep device ecosystem, and privacy-first automation engine.

---

## 🗺️ Phases & Milestones

### Phase 1: Core Foundation & Resilient Pairing *(Completed — v1.0.0 to v1.0.4)*
*Goal: Rock-solid setup on Home Assistant OS with zero-configuration authentication and reliable 24/7 background operation.*

- [x] **Native HA OS Add-on Architecture**: Debian Bookworm container with BlueZ, GLib/D-Bus, Supervisor API proxy, and unprivileged execution.
- [x] **Typed Tool Calling Bridge**: Exposes `homeassistant.call_service`, `homeassistant.get_state`, `homeassistant.list_states`, and `homeassistant.render_template` directly to Muse in the cloud.
- [x] **BlueZ AutoPair Agent (`v1.0.3`)**: Implements `org.bluez.Agent1` with `NoInputNoOutput` capability to automatically authorize and confirm iOS Security Manager (SMP) pairing requests without connection drops.
- [x] **Android MTU Clamping**: Clamps ATT MTU to 256 bytes to prevent Android 14/15 512-byte GATT attribute length exceptions.
- [x] **Connection Forensics & Diagnostic HUD**: Real-time stage logging in Home Assistant Log tab, tracking every step of Bluetooth LE pairing with drop diagnostics.
- [x] **Reconnection Grace Period**: 60-second crypto session preservation across momentary BLE disconnects.
- [x] **Direct Credentials Import (`pairing_json`)**: Allows pasting raw `pairing.json` into add-on configuration to bypass BLE entirely for hardware without Bluetooth.
- [x] **Automatic Meta Muse Chat Welcome Announcement (`v1.0.4`)**: Automatically queries Home Assistant entity counts and introduces the gadget directly into the user's Meta Muse chat upon connecting.
- [x] **24/7 Background Persistence**: Automated 3-hour token rotation daemon, auto-start on boot (`boot: auto`), and zero Bluetooth requirement after initial setup.

---

### Phase 2: Area Awareness, Filtering & Proactive Notifications *(Completed — v1.1.0)*
*Goal: Deep contextual intelligence about your home layout and bidirectional alerts.*

- [x] **Area & Room Intelligence**:
  - Expose Home Assistant areas/floors directly to Muse (`homeassistant.list_areas`, `homeassistant.get_area_devices`).
  - Supports area-level service targets in `homeassistant.call_service`.
  - Enables intuitive room-level queries:
    - *"Turn off everything in the Master Bedroom."*
    - *"What devices are in the kitchen?"*
    - *"What's the temperature in the nursery?"*
- [x] **Smart Entity Summaries for Large Homes (500+ entities)**:
  - Added area and domain filtering with pagination (`limit`, `offset`, `has_more`) to `homeassistant.list_states` so massive entity registries fit cleanly within the 96 KiB Noise frame limit without truncating devices.
- [x] **Bidirectional Notifications (`notify.muse`)**:
  - Built-in lightweight async HTTP webhook on port 8099 (`POST /notify`), plus `homeassistant.notify_muse` tool and `muse-notify` CLI.
  - Allows Home Assistant automations to push proactive natural-language updates straight to your Meta Muse chat:
    - *"Garage door has been open for 15 minutes."*
    - *"Severe weather alert detected for your area."*
    - *"EV has finished charging to 80%."*
- [x] **Device Energy & Power Telemetry**:
  - Added specialized `homeassistant.get_energy` query for Home Assistant's Energy Dashboard (current grid consumption, solar generation, battery level).

---

### Phase 3: Conversational Intelligence & Assist Pipeline *(Target: v1.2.0)*
*Goal: Hybrid intelligence leveraging both Home Assistant Assist and Meta Muse.*

- [ ] **Home Assistant Assist Pipeline Bridge**:
  - Option to route simple intent queries through Home Assistant's built-in `conversation.process` engine for instantaneous execution of local aliases and sentences.
- [ ] **Official Upstream Meta Muse Skill Submission**:
  - Package and submit `gadget-home-assistant/SKILL.md` to the official [`facebookincubator/muse-gadget-sdk`](https://github.com/facebookincubator/muse-gadget-sdk) community catalog.
- [ ] **Conversation History Memory Sync**:
  - Allow Muse to persist home context across app restarts using local gadget state.
- [ ] **Context-Aware Entity Ambiguity Resolution**:
  - Teach Muse to resolve vague requests (e.g., *"turn on the lamp"* when there are 3 lamps) by asking for clarification or checking recent room presence.

---

### Phase 4: Lovelace UI Card & Multi-User Governance *(Target: v1.3.0)*
*Goal: Native dashboard monitoring, security scoping, and user controls.*

- [ ] **Home Assistant Dashboard Card**:
  - Custom Lovelace card showing Meta Muse connection status, active session duration, token expiration time, and last invoked command.
- [ ] **Multi-User Permission & Entity Scoping**:
  - Allow users to restrict which Home Assistant domains or entities Muse is authorized to view or toggle (e.g. expose lights and climate, but protect alarm panels and door locks).
- [ ] **Offline / Local Fallback**:
  - Graceful degradation when the cloud Noise tunnel is unreachable, providing fallback voice control via local Assist.

---

## 💬 Community & Feedback

We welcome feature requests, bug reports, and ideas!
- **Discussion Board**: Share ideas and workflows in [GitHub Discussions](https://github.com/Josh-Archer/homeassistant-addon-muse-gadget/discussions).
- **Issue Tracker**: Report bugs and track milestone progress in [GitHub Issues](https://github.com/Josh-Archer/homeassistant-addon-muse-gadget/issues).
