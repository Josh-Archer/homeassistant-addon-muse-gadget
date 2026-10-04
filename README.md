# Home Assistant Add-ons: Meta Muse Gadget

This repository provides Home Assistant OS add-ons for integrating **Meta Muse** personal AI agents with Home Assistant using the open-source **[Muse Gadget SDK](https://github.com/facebookincubator/muse-gadget-sdk)**.

---

## Add-ons in this Repository

| Add-on | Description |
|---|---|
| **[Muse Gadget](./muse-gadget)** | Connects Home Assistant directly to your Meta Muse agent with automatic chat priming, native tool calling, and 24/7 background persistence. |

---

## Key Features

- **Automatic Chat Welcome Announcement:** Automatically introduces Home Assistant into your Meta Muse mobile chat upon connecting, priming Muse's LLM with your entities and capabilities.
- **Native Smart Home Tool Calling:** Exposes typed tools (`homeassistant.call_service`, `homeassistant.get_state`, `homeassistant.list_states`, `homeassistant.render_template`) directly to your Muse agent in the cloud.
- **Zero-Setup Authentication:** Uses the Home Assistant Supervisor API proxy (`homeassistant_api: true`) to automatically authenticate without needing manual long-lived access tokens.
- **24/7 Persistence:**
  - Bluetooth LE is only needed for the 1-minute initial pairing.
  - Device credentials and keys are saved in `/data/pairing.json`, surviving reboots, container updates, and HAOS upgrades.
  - Background token rotation every 3 hours prevents session expiry.
  - Auto-start on boot (`boot: auto`).
- **Built-in BlueZ AutoPair Agent:** Automatically authorizes iOS SMP Bluetooth pairing requests ("Pair with MuseGadget") to prevent setup drops.

---

## Installation

### In Home Assistant (Recommended)

1. Open your Home Assistant instance.
2. Navigate to **Settings > Apps (or Add-ons) > App store**.
3. In the top-right corner, click the three dots (`⋮`) and select **Repositories**.
4. Add the URL of this repository:
   ```text
   https://github.com/Josh-Archer/homeassistant-addon-muse-gadget
   ```
5. Click **Add**, then close the dialog.
6. Find **Muse Gadget** in the store and click **Install**.
7. Enter your Muse SDK token from [gadgets.muse.ai/settings/sdk-tokens](https://gadgets.muse.ai/settings/sdk-tokens) in the Configuration tab.
8. Click **Start** and follow the pairing steps in the add-on log tab.

---

## License

Apache-2.0 License.
