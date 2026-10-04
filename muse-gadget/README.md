# Home Assistant Add-on: Muse Gadget

Connect your Home Assistant setup directly to your personal **Meta Muse AI agent** using Meta's official open-source [Muse Gadget SDK](https://github.com/facebookincubator/muse-gadget-sdk).

## Features

- **Native Home Assistant Tools**: Exposes typed tools (`homeassistant.call_service`, `homeassistant.get_state`, `homeassistant.list_states`, `homeassistant.render_template`) directly to your Muse agent in the cloud.
- **Natural Voice Control**: Ask Muse to turn on lights, check the temperature, trigger scenes, adjust blinds, or run automations.
- **Zero-Setup Authentication**: Uses the Home Assistant Supervisor API proxy (`homeassistant_api: true`) to automatically authenticate without needing manual long-lived access tokens.
- **Persistent Pairing**: Credentials and identity are saved across add-on reboots and HAOS updates in `/data`.
- **Host Bluetooth LE**: Leverages your host's Bluetooth adapter via D-Bus for fast pairing with the Meta Muse mobile app.
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
     >>> [READY FOR PHONE] Open the Meta Muse app -> Settings -> Devices -> Add Device (+)
         Select: MuseGadgetXXXXXX
     ```

3. **Pair with the Meta Muse Phone App**:
   - Open the **Meta Muse app** on iOS or Android.
   - Go to **Settings > Devices** and enable **Developer mode**.
   - Tap **Add Device (`+`)** in the top right.
   - Select your device (it will appear as `MuseGadgetXXXXXX`).
   - **Important**: When the "Community Device" sheet appears ("Continue or Exit"), tap **Continue** to authorize the device.
   - Confirm your local Wi-Fi when prompted.

4. **Ready!**:
   - The device will complete pairing, save credentials to `/data/pairing.json`, and establish an encrypted session to your Muse cloud VM.

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

---

## Supported Muse Commands

Once paired, you can speak directly to Muse:

- *"Muse, turn off all the lights in the living room."*
- *"Muse, what is the temperature downstairs?"*
- *"Muse, set the thermostat to 72 degrees."*
- *"Muse, activate Movie Night scene."*
