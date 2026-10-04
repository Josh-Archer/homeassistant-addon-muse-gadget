# Home Assistant Add-on: Muse Gadget

Connect your Home Assistant setup directly to your personal **Meta Muse AI agent** using Meta's official open-source [Muse Gadget SDK](https://github.com/facebookincubator/muse-gadget-sdk).

## Features

- **Native Home Assistant Tools**: Exposes typed tools (`homeassistant.call_service`, `homeassistant.get_state`, `homeassistant.list_states`, `homeassistant.render_template`) directly to your Muse agent in the cloud.
- **Automatic Welcome Announcement**: As soon as the add-on connects, it sends an introductory welcome message to your Meta Muse chat with your entity count and device domains, immediately priming Muse's LLM context so it knows how to control your smart home.
- **Natural Voice & Chat Control**: Ask Muse to turn on lights, check temperatures, trigger scenes, adjust blinds, or run automations.
- **Zero-Setup Authentication**: Uses the Home Assistant Supervisor API proxy (`homeassistant_api: true`) to automatically authenticate without needing manual long-lived access tokens.
- **Permanent 24/7 Persistence**:
  - Bluetooth LE is **only used once for the initial 1-minute pairing**.
  - Credentials and identity are saved in `/data/pairing.json`, surviving reboots, container updates, and HAOS upgrades.
  - Automatically starts on system boot (`boot: auto`).
  - Automatic token rotation every 3 hours prevents session expiry.
  - Self-healing reconnection with exponential backoff if your network drops.
- **Built-in AutoPair Agent**: Automatically handles iOS SMP Bluetooth pairing requests ("Pair with MuseGadget") to prevent connection drops.
- **Pairing Diagnostic HUD**: Real-time stage logging, MTU negotiation diagnostics, and connection forensics in the Add-on Log tab.

---

## Configuration

In Home Assistant, navigate to **Settings > Add-ons (or Apps) > Muse Gadget > Configuration**:

| Option | Type | Required | Description |
|---|---|---|---|
| `sdk_token` | `string` | **Yes** | Your Muse SDK token from [gadgets.muse.ai/settings/sdk-tokens](https://gadgets.muse.ai/settings/sdk-tokens). |
| `ha_url` | `string` | No | Home Assistant API URL. Defaults to `http://supervisor/core/api`. |
| `ha_token` | `password` | No | Optional Long-Lived Access Token if connecting to an external HA instance. |
| `pairing_json` | `password` | No | Optional. Paste raw `pairing.json` content here to bypass BLE setup if paired on another machine. |

---

## Setup & Pairing Walkthrough

1. **Get an SDK Token**:
   - Go to [https://gadgets.muse.ai/settings/sdk-tokens](https://gadgets.muse.ai/settings/sdk-tokens).
   - Generate a token (format: `mgst_...`).
   - Paste it into the `sdk_token` field in the add-on configuration and click **Save**.

2. **Start the Add-on & Watch the Log**:
   - Go to the **Info** tab and click **Start**.
   - Open the **Log** tab. You will see:
     ```text
     >>> [BLUETOOTH ADAPTER READY]
     >>> [BLUETOOTH AGENT READY] AutoPair agent registered ('NoInputNoOutput')
     >>> [READY FOR PHONE] Open the Meta Muse app -> Settings -> Devices -> Add Device (+)
         Select: MuseGadgetXXXXXX
     ```

3. **Pair with the Meta Muse Phone App**:
   - Open the **Meta Muse app** on iOS or Android.
   - Go to **Settings > Devices** and enable **Developer mode**.
   - Tap **Add Device (`+`)** in the top right.
   - Select your device (it will appear as `MuseGadgetXXXXXX`).
   - Tap **Continue** on the "Community Device" sheet.
   - Tap **Pair** when the iOS Bluetooth Pairing Request appears.
   - Confirm your local Wi-Fi when prompted.

4. **Automatic Welcome & Ready!**:
   - The device completes pairing, saves credentials to `/data/pairing.json`, and connects via encrypted Noise WebSocket to your Muse cloud VM.
   - Once connected, Home Assistant automatically sends a welcome message into your Meta Muse mobile chat:
     > *"Home Assistant is online and connected via your Muse Gadget (homelink-XXXXXX)! Found 35 smart entities (climate, light, sensor, switch). You can ask me to check device states, turn lights on or off, adjust thermostats, or trigger scenes."*
   - Muse responds in the chat acknowledging your home devices and is instantly primed for voice and text control!

---

## 24/7 Persistence & Reliability

Once pairing succeeds, your setup is **permanent**:
- **No Bluetooth Needed:** Bluetooth LE radio is completely deactivated after setup. All control operates over your local network and the internet.
- **Survives Reboots:** The add-on runs as an auto-boot service (`boot: auto`). When Home Assistant OS updates or restarts, the add-on reconnects within seconds.
- **Background Token Refresh:** Meta device tokens expire every 4 hours. The add-on daemon refreshes tokens in the background every 3 hours and updates `/data/pairing.json`.
- **Zero Maintenance:** If your router or home internet restarts, the daemon automatically reconnects in the background.

---

## Supported Muse Commands & Examples

You can speak or type to Muse naturally in your mobile app:

### Device Queries & States
- *"What lights are currently on?"*
- *"What is the indoor temperature?"*
- *"Are all the doors locked?"*
- *"Is anyone in the living room?"*

### Smart Device Control
- *"Turn off all the lights downstairs."*
- *"Set the kitchen light brightness to 70%."*
- *"Set the hallway thermostat to 72 degrees."*
- *"Turn on the patio string lights."*

### Scenes & Automations
- *"Activate Movie Night scene."*
- *"Trigger Goodnight routine."*

---

## Troubleshooting & Tips

### iOS Sheet Dismisses or Drops to Device List
If you tap the device on your iPhone and the "Community Device" popup dismisses itself after 1–2 seconds:

1. **Home Assistant Bluetooth Conflict**:
   Home Assistant Core runs continuous active scanning on `hci0` to discover smart home sensors. Active scanning can cause BLE peripheral connection packet loss.
   - Go to **Settings → Devices & Services → Integrations**.
   - Find the **Bluetooth** integration, click the three dots (`⋮`), and select **Disable**.
   - Return to the Meta Muse app and pair your device.
   - Once paired, re-enable the Bluetooth integration! (BLE is only used for the initial 1-minute pairing; Muse uses cloud Wi-Fi/Ethernet thereafter).

2. **Signal Proximity**:
   Ensure your phone is within 1–2 feet of your Home Assistant server during pairing.

3. **Alternative Desktop Pairing (Bypass BLE entirely)**:
   If your Home Assistant hardware has weak Bluetooth:
   - Run `musegadget pair` on your desktop/laptop (which has Bluetooth).
   - Complete pairing with your phone on your computer.
   - Copy the generated `pairing.json` and paste its contents into the add-on's `pairing_json` configuration option.
   - Save and start the add-on — it will instantly connect to your Meta Muse agent!
