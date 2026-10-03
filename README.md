# Home Assistant Add-ons: Meta Muse Gadget

This repository provides Home Assistant OS add-ons for integrating **Meta Muse** personal AI agents with Home Assistant using the open-source **[Muse Gadget SDK](https://github.com/facebookincubator/muse-gadget-sdk)**.

---

## Add-ons in this Repository

| Add-on | Description |
|---|---|
| **[Muse Gadget](./muse-gadget)** | Connects Home Assistant directly to your Meta Muse agent via Bluetooth LE and encrypted cloud Noise session. |

---

## Installation

### Option 1: Add as a Custom Repository in Home Assistant (Recommended)

1. Open your Home Assistant instance.
2. Navigate to **Settings > Add-ons > Add-on Store**.
3. In the top-right corner, click the three dots (`⋮`) and select **Repositories**.
4. Add the URL of this repository:
   ```
   https://github.com/Josh-Archer/homeassistant-addon-muse-gadget
   ```
5. Click **Add**, then close the dialog.
6. The store will reload, and **Muse Gadget** will appear in your Add-on Store.
7. Click **Muse Gadget** → **Install**.

---

### Option 2: Local Add-on (Direct Copy)

If your Home Assistant OS instance has Samba or SSH enabled:

1. Copy the `muse-gadget` folder to `/addons/muse_gadget` on your Home Assistant machine.
2. In Home Assistant, go to **Settings > Add-ons > Add-on Store**.
3. Click `⋮` in the top right → **Check for updates**.
4. Install **Muse Gadget** under the **Local add-ons** section.

---

## License

Apache-2.0 License.
