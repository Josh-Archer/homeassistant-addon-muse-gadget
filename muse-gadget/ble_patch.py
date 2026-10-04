"""BLE Server and SetupController stability and rich logging patches for Home Assistant OS.

Features:
1. Step-by-Step Pairing HUD: Logs clear human-readable milestones for every stage of pairing.
2. BlueZ AutoPair Agent: Automatically confirms and authorizes iOS SMP pairing requests ("Pair with MuseGadget").
3. Adapter & Connection Diagnostics: Logs adapter properties, MTU negotiations, and connection durations.
4. Disconnect Forensics: Pinpoints why and at what stage a disconnection occurred, with actionable tips.
5. BlueZ Stability Fixes: Sets Pairable=True, Discoverable=True, and marks phones as Trusted.
6. Session Grace Period: Preserves confirmed sessions across brief BLE reconnects (60s grace).
7. MTU Clamping: Limits ATT MTU to 256 bytes to prevent packet overflow.
8. Notification Pacing: Paces notifications at 80ms to avoid BLE controller buffer drops.
"""

from __future__ import annotations

import json
import logging
import signal
import threading
import time
from typing import Callable

import dbus
import dbus.service
from gi.repository import GLib

import musegadget.ble_framing as ble_framing
import musegadget.ble_server as ble_server
import musegadget.ble_setup as ble_setup
from musegadget.ble_server import (
    ADAPTER_IFACE,
    BLUEZ_SERVICE,
    DBUS_PROP_IFACE,
    DEVICE_IFACE,
    GATT_MANAGER_IFACE,
    LE_ADV_MANAGER_IFACE,
    APP_PATH,
    ADV_PATH,
    BleServer,
)
from musegadget.ble_setup import SetupController

log = logging.getLogger("musegadget.ble")

AGENT_PATH = "/org/musegadget/agent"
AGENT_IFACE = "org.bluez.Agent1"
AGENT_MGR_IFACE = "org.bluez.AgentManager1"

# Session tracking for disconnect diagnostics
_connection_start_time: float = 0.0
_current_stage: str = "WAITING_FOR_DISCOVERY"


class AutoPairAgent(dbus.service.Object):
    """BlueZ D-Bus Agent that automatically authorizes and confirms pairing requests.

    When an iPhone connects and displays the system 'Pair with MuseGadget' popup,
    iOS initiates an SMP (Security Manager Protocol) handshake. This agent responds
    instantly with 'Just Works' confirmation so pairing succeeds without dropped connections.
    """

    def __init__(self, bus: dbus.SystemBus):
        super().__init__(bus, AGENT_PATH)

    @dbus.service.method(AGENT_IFACE, in_signature="", out_signature="")
    def Release(self):
        log.info("Pairing agent released by BlueZ")

    @dbus.service.method(AGENT_IFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        log.info(">>> [SMP AGENT] Auto-authorized service %s for %s", uuid, device)
        return

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        log.info(">>> [SMP AGENT] Auto-authorized pairing for %s", device)
        return

    @dbus.service.method(AGENT_IFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        log.info(">>> [SMP AGENT] Auto-confirmed passkey %06d for %s (Pairing accepted!)", passkey, device)
        return

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        log.info(">>> [SMP AGENT] Passkey requested for %s -> returning 000000", device)
        return dbus.UInt32(0)

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        log.info(">>> [SMP AGENT] PIN requested for %s -> returning '0000'", device)
        return "0000"

    @dbus.service.method(AGENT_IFACE, in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        log.info(">>> [SMP AGENT] Display passkey: %06d (entered: %d) for %s", passkey, entered, device)

    @dbus.service.method(AGENT_IFACE, in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        log.info(">>> [SMP AGENT] Display PIN: %s for %s", pincode, device)

    @dbus.service.method(AGENT_IFACE, in_signature="", out_signature="")
    def Cancel(self):
        log.info(">>> [SMP AGENT] Pairing canceled by peer")


def apply_ble_patches() -> None:
    log.info("==================================================================")
    log.info(" Loading Muse Gadget BLE Diagnostics & Stability Engine v1.0.3")
    log.info("==================================================================")

    # 1. Pacing: Increase packet notification stagger to 80ms
    ble_framing.CHUNK_STAGGER_S = 0.08

    # 2. Patch BleServer.run with BlueZ AutoPair Agent and stability properties
    def patched_run(self: BleServer) -> None:
        global _current_stage
        _current_stage = "ADVERTISING_BEACON"
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = self._bus = dbus.SystemBus()
        self._adapter_path = ble_server._find_adapter(bus)
        adapter = dbus.Interface(bus.get_object(BLUEZ_SERVICE, self._adapter_path), DBUS_PROP_IFACE)
        self._saved_adapter = {k: adapter.Get(ADAPTER_IFACE, k) for k in ("Alias", "Pairable")}

        # Adapter properties: keep powered, set alias and pairable/discoverable
        adapter.Set(ADAPTER_IFACE, "Powered", dbus.Boolean(True))
        adapter.Set(ADAPTER_IFACE, "Alias", dbus.String(self._local_name))
        adapter.Set(ADAPTER_IFACE, "Pairable", dbus.Boolean(True))
        try:
            adapter.Set(ADAPTER_IFACE, "PairableTimeout", dbus.UInt32(0))
            adapter.Set(ADAPTER_IFACE, "Discoverable", dbus.Boolean(True))
            adapter.Set(ADAPTER_IFACE, "DiscoverableTimeout", dbus.UInt32(0))
        except Exception as exc:
            log.debug("Optional adapter properties not set: %s", exc)

        # Register BlueZ AutoPair Agent to handle iOS SMP pairing requests
        self._agent_obj = None
        try:
            agent_mgr = dbus.Interface(bus.get_object(BLUEZ_SERVICE, "/org/bluez"), AGENT_MGR_IFACE)
            try:
                agent_mgr.UnregisterAgent(AGENT_PATH)
            except Exception:
                pass
            self._agent_obj = AutoPairAgent(bus)
            agent_mgr.RegisterAgent(AGENT_PATH, "NoInputNoOutput")
            agent_mgr.RequestDefaultAgent(AGENT_PATH)
            log.info(">>> [BLUETOOTH AGENT READY] AutoPair agent registered ('NoInputNoOutput')")
            log.info("    Status: Ready to auto-confirm iOS pairing requests")
        except Exception as exc:
            log.warning("Could not register BlueZ pairing agent: %s", exc)

        log.info(">>> [BLUETOOTH ADAPTER READY]")
        log.info("    Adapter Path : %s", self._adapter_path)
        log.info("    Device Name  : %s", self._local_name)
        log.info("    Pairable     : True (iOS CoreBluetooth SMP enabled)")
        log.info("    Discoverable : True (Continuous beacon)")
        log.info("------------------------------------------------------------------")
        log.info(">>> [READY FOR PHONE] Open the Meta Muse app -> Settings -> Devices -> Add Device (+)")
        log.info("    Select: %s", self._local_name)
        log.info("------------------------------------------------------------------")

        app = ble_server.Application(bus)
        service = ble_server.Service(bus, 0, ble_server.SERVICE_UUID)
        service.characteristics.append(ble_server.Characteristic(
            bus, service, 0, ble_server.RX_UUID, ["write", "write-without-response"], on_write=self._handle_write,
        ))
        self._tx = ble_server.Characteristic(bus, service, 1, ble_server.TX_UUID, ["read", "notify"])
        service.characteristics.append(self._tx)
        app.services.append(service)
        self._objects = (app, service, self._tx, ble_server.Advertisement(bus, self._local_name))

        bus.add_signal_receiver(
            self._handle_device_change,
            dbus_interface=DBUS_PROP_IFACE,
            signal_name="PropertiesChanged",
            arg0=DEVICE_IFACE,
            path_keyword="path",
        )
        adapter_obj = bus.get_object(BLUEZ_SERVICE, self._adapter_path)
        dbus.Interface(adapter_obj, GATT_MANAGER_IFACE).RegisterApplication(
            APP_PATH, {},
            reply_handler=lambda: log.info("GATT service registered"),
            error_handler=lambda e: self._fatal("GATT registration failed", e),
        )
        dbus.Interface(adapter_obj, LE_ADV_MANAGER_IFACE).RegisterAdvertisement(
            ADV_PATH, {},
            reply_handler=lambda: log.info("advertising as %s", self._local_name),
            error_handler=lambda e: self._fatal("advertising failed", e),
        )
        self._loop = GLib.MainLoop()
        for signum in (signal.SIGTERM, signal.SIGINT):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signum, self._loop.quit)
        try:
            self._loop.run()
        finally:
            if self._agent_obj:
                try:
                    agent_mgr = dbus.Interface(bus.get_object(BLUEZ_SERVICE, "/org/bluez"), AGENT_MGR_IFACE)
                    agent_mgr.UnregisterAgent(AGENT_PATH)
                    log.info("Unregistered AutoPair agent")
                except Exception:
                    pass
            self._teardown()

    BleServer.run = patched_run

    # 3. Patch BleServer._handle_write with write logging & MTU clamp
    orig_handle_write = BleServer._handle_write

    def patched_handle_write(self: BleServer, value: bytes, options: dict) -> None:
        with self._lock:
            if "mtu" in options:
                negotiated = int(options["mtu"])
                self._mtu = min(negotiated, 256)
                log.info(">>> [GATT ATT MTU] Negotiated: %d bytes (Clamped to safe: %d bytes)", negotiated, self._mtu)
            if "device" in options:
                self._device_path = str(options["device"])
        self._on_write(value)

    BleServer._handle_write = patched_handle_write

    # 4. Patch BleServer._handle_device_change with connection tracking and Trusted status
    orig_handle_device_change = BleServer._handle_device_change

    def patched_handle_device_change(self: BleServer, interface, changed, invalidated, path=None):
        global _connection_start_time, _current_stage

        if changed.get("Connected") is True:
            _connection_start_time = time.monotonic()
            _current_stage = "CONNECTED_GATT_INIT"
            log.info("******************************************************************")
            log.info(">>> [PHONE CONNECTED] BLE Client: %s", path)
            log.info("******************************************************************")
            if path and self._bus:
                try:
                    dev_obj = self._bus.get_object(BLUEZ_SERVICE, path)
                    dev_props = dbus.Interface(dev_obj, DBUS_PROP_IFACE)
                    dev_props.Set(DEVICE_IFACE, "Trusted", dbus.Boolean(True))
                    log.info("    Status: Marked as 'Trusted' device in BlueZ")
                except Exception as exc:
                    log.debug("Could not set Trusted on %s: %s", path, exc)

        if changed.get("Connected") is False:
            duration = time.monotonic() - _connection_start_time if _connection_start_time > 0 else 0.0
            log.info("------------------------------------------------------------------")
            log.info(">>> [PHONE DISCONNECTED] Connection closed after %.2f seconds", duration)
            log.info("    Last Stage Reached : %s", _current_stage)
            if duration < 3.0 and _current_stage in ("DEVICE_INFO_SENT", "WAITING_FOR_USER_CONSENT", "CONNECTED_GATT_INIT"):
                log.warning("    ==============================================================")
                log.warning("    [DIAGNOSTIC ADVICE - QUICK DISCONNECT DETECTED (%.1fs)]", duration)
                log.warning("    The phone disconnected before pairing completed.")
                log.warning("    1. HOME ASSISTANT BLUETOOTH SCANNER CONFLICT:")
                log.warning("       Home Assistant Core actively scans on the same Bluetooth adapter.")
                log.warning("       Temporarily disable it during pairing:")
                log.warning("       Go to Settings -> Devices & Services -> Bluetooth -> ⋮ -> Disable.")
                log.warning("       Re-enable it after pairing completes.")
                log.warning("    2. DISTANCE / SIGNAL:")
                log.warning("       Hold your iPhone within 1 to 2 feet of the Home Assistant hardware.")
                log.warning("    3. ALTERNATIVE DESKTOP PAIRING:")
                log.warning("       You can also run 'musegadget pair' on your desktop computer and")
                log.warning("       paste the resulting pairing.json into the Add-on Configuration tab.")
                log.warning("    ==============================================================")
            log.info("------------------------------------------------------------------")

        orig_handle_device_change(self, interface, changed, invalidated, path=path)

    BleServer._handle_device_change = patched_handle_device_change

    # 5. Patch SetupController.handle_message with Human-Readable Stage HUD
    orig_handle_message = SetupController.handle_message

    def patched_handle_message(self: SetupController, raw: bytes, decrypted: bool = False) -> None:
        global _current_stage
        try:
            parsed = json.loads(raw.decode("utf-8"))
            action = parsed.get("action")
            if action == "get_device_info":
                _current_stage = "DEVICE_INFO_SENT"
                log.info(">>> [PAIRING STEP 1/3] Phone requested device metadata ('get_device_info'). Sent.")
                log.info("==================================================================")
                log.info(" [ACTION REQUIRED ON IPHONE NOW]")
                log.info(" 1. Tap 'Continue' on the 'Community Device' popup.")
                log.info(" 2. Tap 'Pair' when the iOS Bluetooth Pairing Request appears!")
                log.info("==================================================================")
            elif action == "pairing_client_hello":
                _current_stage = "KEY_EXCHANGE_HELLO"
                log.info(">>> [PAIRING STEP 2/3] User tapped Continue! iPhone initiated encrypted ECDH handshake.")
            elif action == "pairing_client_finished":
                _current_stage = "WAITING_FOR_PROVISION"
                log.info(">>> [PAIRING STEP 3/3] Client handshake verified! Session confirmed.")
                log.info(">>> Waiting for Wi-Fi and token provisioning ('provision_v2') from iPhone...")
            elif action == "wifi_scan":
                _current_stage = "WIFI_SCAN_REQUESTED"
                log.info(">>> [PAIRING PROGRESS] iPhone requested Wi-Fi networks. Responding with active link.")
            elif action == "provision_v2":
                _current_stage = "PROVISIONING_RECEIVED"
                log.info(">>> [FINAL STEP] Received device tokens and account credentials from Meta!")
                log.info("    Saving pairing.json to /data...")
        except Exception:
            pass

        orig_handle_message(self, raw, decrypted)

    SetupController.handle_message = patched_handle_message

    # 6. Patch SetupController.on_disconnect with 60-second confirmed session preservation
    orig_on_disconnect = SetupController.on_disconnect
    disconnect_timer: list[threading.Timer | None] = [None]

    def patched_on_disconnect(self: SetupController) -> None:
        if self._pairing.confirmed:
            log.info(">>> [RECONNECTION GRACE ACTIVE]")
            log.info("    Pairing session is CONFIRMED. Keeping crypto session alive for 60 seconds.")
            log.info("    If your iPhone reconnects now, setup will seamlessly resume.")
            if disconnect_timer[0]:
                disconnect_timer[0].cancel()

            def delayed_wipe():
                log.info(">>> Reconnection grace period expired (60s). Clearing pairing session.")
                self._assembler.reset()
                with self._state_lock:
                    self._plaintext_blocked = False
                self._pairing.reset()

            t = threading.Timer(60.0, delayed_wipe)
            disconnect_timer[0] = t
            t.daemon = True
            t.start()
            return

        log.info(">>> Clearing unconfirmed pairing session.")
        orig_on_disconnect(self)

    SetupController.on_disconnect = patched_on_disconnect

    orig_on_write = SetupController.on_write

    def patched_on_write(self: SetupController, packet: bytes) -> None:
        if disconnect_timer[0]:
            log.info(">>> [PHONE RECONNECTED] Canceling expiration timer and resuming pairing!")
            disconnect_timer[0].cancel()
            disconnect_timer[0] = None
        orig_on_write(self, packet)

    SetupController.on_write = patched_on_write

    log.info("BLE Diagnostics and Stability Patches successfully activated.")
