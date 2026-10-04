"""BLE Server and SetupController stability patches for Home Assistant OS and iOS/Android.

Resolves connection dropping, MTU overflow, and premature session resets:
1. Enables Pairable and Discoverable on BlueZ adapter (prevents iOS disconnect on SMP check).
2. Auto-marks connecting phone as 'Trusted' in BlueZ.
3. Clamps ATT MTU to 256 to avoid Android/iOS GATT attribute length errors.
4. Prevents immediate session wipe on disconnect when pairing is already confirmed (60s grace period).
5. Increases notification pacing to 80ms to avoid BLE controller buffer drops.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import dbus
from gi.repository import GLib

import musegadget.ble_framing as ble_framing
import musegadget.ble_server as ble_server
import musegadget.ble_setup as ble_setup
from musegadget.ble_server import (
    ADAPTER_IFACE,
    BLUEZ_SERVICE,
    DBUS_PROP_IFACE,
    DEVICE_IFACE,
    BleServer,
)
from musegadget.ble_setup import SetupController

log = logging.getLogger("musegadget.ble_patch")


def apply_ble_patches() -> None:
    log.info("Applying stability patches to BlueZ BLE server and SetupController...")

    # 1. Pacing: Increase packet notification stagger to 80ms
    ble_framing.CHUNK_STAGGER_S = 0.08

    # 2. Patch BleServer.run to make adapter Pairable and Discoverable
    orig_run = BleServer.run

    def patched_run(self: BleServer) -> None:
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = self._bus = dbus.SystemBus()
        self._adapter_path = ble_server._find_adapter(bus)
        adapter = dbus.Interface(bus.get_object(BLUEZ_SERVICE, self._adapter_path), DBUS_PROP_IFACE)
        self._saved_adapter = {k: adapter.Get(ADAPTER_IFACE, k) for k in ("Alias", "Pairable")}

        adapter.Set(ADAPTER_IFACE, "Powered", dbus.Boolean(True))
        adapter.Set(ADAPTER_IFACE, "Alias", dbus.String(self._local_name))
        # Allow pairing so iOS CoreBluetooth does not terminate when initiating security
        adapter.Set(ADAPTER_IFACE, "Pairable", dbus.Boolean(True))
        try:
            adapter.Set(ADAPTER_IFACE, "PairableTimeout", dbus.UInt32(0))
            adapter.Set(ADAPTER_IFACE, "Discoverable", dbus.Boolean(True))
            adapter.Set(ADAPTER_IFACE, "DiscoverableTimeout", dbus.UInt32(0))
        except Exception as exc:
            log.debug("Optional adapter properties not set: %s", exc)

        log.info("Configured BlueZ adapter: Powered=True, Pairable=True, Discoverable=True")

        orig_run(self)

    BleServer.run = patched_run

    # 3. Patch BleServer._handle_write to clamp MTU to 256
    orig_handle_write = BleServer._handle_write

    def patched_handle_write(self: BleServer, value: bytes, options: dict) -> None:
        with self._lock:
            if "mtu" in options:
                negotiated = int(options["mtu"])
                self._mtu = min(negotiated, 256)
                log.info("ATT MTU %d (clamped to %d)", negotiated, self._mtu)
            if "device" in options:
                self._device_path = str(options["device"])
        self._on_write(value)

    BleServer._handle_write = patched_handle_write

    # 4. Patch BleServer._handle_device_change to auto-trust connected devices
    orig_handle_device_change = BleServer._handle_device_change

    def patched_handle_device_change(self: BleServer, interface, changed, invalidated, path=None):
        if changed.get("Connected") is True and path and self._bus:
            log.info("BLE device connected: %s", path)
            try:
                dev_obj = self._bus.get_object(BLUEZ_SERVICE, path)
                dev_props = dbus.Interface(dev_obj, DBUS_PROP_IFACE)
                dev_props.Set(DEVICE_IFACE, "Trusted", dbus.Boolean(True))
                log.info("Marked BLE device %s as Trusted", path)
            except Exception as exc:
                log.debug("Could not set Trusted on %s: %s", path, exc)

        orig_handle_device_change(self, interface, changed, invalidated, path=path)

    BleServer._handle_device_change = patched_handle_device_change

    # 5. Patch SetupController.on_disconnect to grant a 60s grace period if confirmed
    orig_on_disconnect = SetupController.on_disconnect
    disconnect_timer: list[threading.Timer | None] = [None]

    def patched_on_disconnect(self: SetupController) -> None:
        if self._pairing.confirmed:
            log.info("BLE client disconnected, but session is confirmed. Keeping session alive for 60s for reconnection...")
            if disconnect_timer[0]:
                disconnect_timer[0].cancel()

            def delayed_wipe():
                log.info("Reconnection grace period expired; clearing pairing session")
                self._assembler.reset()
                with self._state_lock:
                    self._plaintext_blocked = False
                self._pairing.reset()

            t = threading.Timer(60.0, delayed_wipe)
            disconnect_timer[0] = t
            t.daemon = True
            t.start()
            return

        log.info("BLE client disconnected; clearing unconfirmed pairing session")
        orig_on_disconnect(self)

    SetupController.on_disconnect = patched_on_disconnect

    orig_on_write = SetupController.on_write

    def patched_on_write(self: SetupController, packet: bytes) -> None:
        if disconnect_timer[0]:
            disconnect_timer[0].cancel()
            disconnect_timer[0] = None
        orig_on_write(self, packet)

    SetupController.on_write = patched_on_write

    log.info("BLE stability patches successfully applied.")
