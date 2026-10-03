# Home Assistant Add-on: Muse Gadget

Connect your Home Assistant setup directly to your personal **Meta Muse AI agent** using Meta's official open-source [Muse Gadget SDK](https://github.com/facebookincubator/muse-gadget-sdk).

## Features

- **Native Home Assistant Tools**: Exposes typed tools (`homeassistant.call_service`, `homeassistant.get_state`, `homeassistant.list_states`, `homeassistant.render_template`) directly to your Muse agent in the cloud.
- **Natural Voice Control**: Ask Muse to turn on lights, check the temperature, trigger scenes, adjust blinds, or run automations.
- **Zero-Setup Authentication**: Uses the Home Assistant Supervisor API proxy (`homeassistant_api: true`) to automatically authenticate without needing manual long-lived access tokens.
- **Persistent Pairing**: Credentials and identity are saved across add-on reboots and HAOS updates in `/data`.
- **Host Bluetooth LE**: Leverages your host's Bluetooth adapter via D-Bus for fast pairing with the Meta Muse mobile app.

---

## Configuration

In Home Assistant, navigate to **Settings > Add-ons > Muse Gadget > Configuration**:

| Option | Type | Required | Description |
|---|---|---|---|
| `sdk_token` | `string` | **Yes** | Your Muse SDK token from [gadgets.muse.ai/settings/sdk-tokens](https://gadgets.muse.ai/settings/sdk-tokens). |
| `ha_url` | `string` | No | Home Assistant API URL. Defaults to `http://supervisor/core/api`. |
| `ha_token` | `password` | No | Optional Long-Lived Access Token if connecting to an external HA instance. |

---

## Setup & Pairing Walkthrough

1. **Get an SDK Token**:
   - Go to [https://gadgets.muse.ai/settings/sdk-tokens](https://gadgets.muse.ai/settings/sdk-tokens).
   - Generate a token (format: `mgst_...`).
   - Paste it into the `sdk_token` field in the add-on configuration and click **Save**.

2. **Start the Add-on**:
   - Go to the **Info** tab and click **Start**.
   - Open the **Log** tab. You will see:
     ```
     [PAIRING MODE ACTIVATED]
     Starting Bluetooth LE discovery for 10 minutes...
     ```

3. **Pair with the Muse Phone App**:
   - Open the **Meta Muse app** on iOS or Android.
   - Go to **Settings > Devices**.
   - Enable **Developer mode**.
   - Tap **Add Device (`+`)** in the top right.
   - Select your device (it will appear as `MuseGadgetXXXXXX`).
   - Confirm your local Wi-Fi when prompted.

4. **Ready!**:
   - The device will complete pairing, save credentials, and establish an encrypted session to your Muse cloud VM.

---

## Supported Muse Commands

Once paired, you can speak directly to Muse:

- *"Muse, turn off all the lights in the living room."*
- *"Muse, what is the temperature downstairs?"*
- *"Muse, set the thermostat to 72 degrees."*
- *"Muse, activate Movie Night scene."*
