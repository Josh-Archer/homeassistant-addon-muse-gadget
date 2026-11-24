"""Unit tests for BLE patch missing-adapter diagnostics and backoff."""

from __future__ import annotations

import logging
import sys
import time
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure muse-gadget directory is on sys.path dynamically
app_dir = Path(__file__).resolve().parent.parent / "muse-gadget"
if app_dir.exists():
    sys.path.insert(0, str(app_dir))
if Path("/app").exists():
    sys.path.insert(0, "/app")


class TestBlePatchMissingAdapter(unittest.TestCase):
    """Test missing Bluetooth adapter diagnostics and backoff behavior."""

    def setUp(self):
        # Capture log output
        self.log_stream = StringIO()
        self.log_handler = logging.StreamHandler(self.log_stream)
        self.log_handler.setLevel(logging.ERROR)
        formatter = logging.Formatter("%(levelname)s %(name)s: %(message)s")
        self.log_handler.setFormatter(formatter)

        self.logger = logging.getLogger("musegadget.ble")
        self.logger.setLevel(logging.ERROR)
        self.logger.addHandler(self.log_handler)

    def tearDown(self):
        self.logger.removeHandler(self.log_handler)

    @patch("ble_patch.ble_server._find_adapter")
    @patch("ble_patch.time.sleep")
    @patch("ble_patch.dbus.mainloop.glib.DBusGMainLoop")
    @patch("ble_patch.dbus.SystemBus")
    def test_missing_adapter_logs_diagnostic_and_sleeps(
        self, mock_bus, mock_dbus_loop, mock_sleep, mock_find_adapter
    ):
        """When _find_adapter raises RuntimeError, diagnostic is logged and backoff sleeps."""
        from ble_patch import apply_ble_patches

        # Simulate missing adapter
        mock_find_adapter.side_effect = RuntimeError("no Bluetooth adapter found")
        mock_bus.return_value = MagicMock()

        # apply_ble_patches should raise the RuntimeError after logging
        with self.assertRaises(RuntimeError) as cm:
            apply_ble_patches()

        self.assertIn("no Bluetooth adapter found", str(cm.exception))

        # Verify diagnostic message was logged
        log_output = self.log_stream.getvalue()
        self.assertIn("[BLUETOOTH ADAPTER NOT FOUND]", log_output)
        self.assertIn("Initial BLE pairing requires a BlueZ adapter", log_output)
        self.assertIn("lsusb | grep -i bluetooth", log_output)
        self.assertIn("bluetoothctl list", log_output)
        self.assertIn("combo cards expose Bluetooth on USB", log_output)
        self.assertIn("host_dbus: true", log_output)
        self.assertIn("bluetooth: true", log_output)

        # Verify backoff sleep was called (15 seconds)
        mock_sleep.assert_called_with(15)

    @patch("ble_patch.ble_server._find_adapter")
    @patch("ble_patch.time.sleep")
    @patch("ble_patch.dbus.mainloop.glib.DBusGMainLoop")
    @patch("ble_patch.dbus.SystemBus")
    def test_missing_adapter_other_runtime_error_not_caught(
        self, mock_bus, mock_dbus_loop, mock_sleep, mock_find_adapter
    ):
        """Other RuntimeErrors from _find_adapter should not be caught/swallowed."""
        from ble_patch import apply_ble_patches

        mock_find_adapter.side_effect = RuntimeError("some other error")
        mock_bus.return_value = MagicMock()

        with self.assertRaises(RuntimeError) as cm:
            apply_ble_patches()

        self.assertEqual(str(cm.exception), "some other error")
        # Should not have slept
        mock_sleep.assert_not_called()

    @patch("ble_patch.ble_server._find_adapter")
    @patch("ble_patch.dbus.mainloop.glib.DBusGMainLoop")
    @patch("ble_patch.dbus.SystemBus")
    def test_normal_adapter_discovery_works_untouched(
        self, mock_bus, mock_dbus_loop, mock_find_adapter
    ):
        """Normal adapter discovery path should work without interference."""
        from ble_patch import apply_ble_patches

        # Simulate successful adapter discovery
        mock_find_adapter.return_value = "/org/bluez/hci0"
        mock_bus.return_value = MagicMock()

        # Should not raise
        apply_ble_patches()

        # Verify _find_adapter was called
        mock_find_adapter.assert_called_once()
        # No sleep should be called
        # (can't easily mock time.sleep here since it's not patched, but we can verify
        #  by checking the log doesn't contain the diagnostic)
        log_output = self.log_stream.getvalue()
        self.assertNotIn("[BLUETOOTH ADAPTER NOT FOUND]", log_output)


class TestEntrypointMissingAdapter(unittest.TestCase):
    """Test entrypoint.py handling of missing adapter."""

    def setUp(self):
        self.log_stream = StringIO()
        self.log_handler = logging.StreamHandler(self.log_stream)
        self.log_handler.setLevel(logging.ERROR)
        formatter = logging.Formatter("%(levelname)s %(name)s: %(message)s")
        self.log_handler.setFormatter(formatter)

        self.logger = logging.getLogger("musegadget.entrypoint")
        self.logger.setLevel(logging.ERROR)
        self.logger.addHandler(self.log_handler)

    def tearDown(self):
        self.logger.removeHandler(self.log_handler)

    @patch("entrypoint.time.sleep")
    @patch("entrypoint.load_options")
    @patch("entrypoint.Path.exists")
    def test_entrypoint_catches_missing_adapter_logs_and_sleeps(
        self, mock_path_exists, mock_load_options, mock_sleep
    ):
        """Entrypoint should catch missing adapter, log diagnostic, sleep, then re-raise."""
        from entrypoint import main

        # Configure mocks: first call to load_options returns no token (triggers loop),
        # second call returns a token (exits loop)
        mock_load_options.side_effect = [
            {"sdk_token": "mgst_test123"},  # First call - has token
        ]
        # Path.exists for pairing.json returns False (pairing mode)
        mock_path_exists.return_value = False

        # Mock the BLE patch application to raise the missing adapter error
        with patch("ble_patch.apply_ble_patches") as mock_apply:
            mock_apply.side_effect = RuntimeError("no Bluetooth adapter found")

            with self.assertRaises(RuntimeError):
                main()

        # Verify diagnostic was logged
        log_output = self.log_stream.getvalue()
        self.assertIn("[BLUETOOTH ADAPTER NOT FOUND]", log_output)
        self.assertIn("Bluetooth LE is required for the 1-minute initial pairing", log_output)
        self.assertIn("pass through USB Bluetooth device/dongle", log_output)
        self.assertIn("Combo Wi-Fi/BT cards expose Bluetooth on USB", log_output)
        self.assertIn("lsusb | grep -i bluetooth", log_output)
        self.assertIn("bluetoothctl list", log_output)

        # Verify backoff sleep was called (may be called twice - once for sdk_token loop sleep, once for adapter)
        # At least one call with 15 seconds
        calls = mock_sleep.call_args_list
        self.assertTrue(any(c[0][0] == 15 for c in calls), f"Expected sleep(15) call, got {calls}")

    @patch("entrypoint.time.sleep")
    @patch("entrypoint.load_options")
    @patch("entrypoint.Path.exists")
    def test_entrypoint_other_errors_not_caught(
        self, mock_path_exists, mock_load_options, mock_sleep
    ):
        """Other exceptions from apply_ble_patches should not be caught."""
        from entrypoint import main

        mock_load_options.side_effect = [
            {"sdk_token": "mgst_test123"},
        ]
        mock_path_exists.return_value = False

        with patch("ble_patch.apply_ble_patches") as mock_apply:
            mock_apply.side_effect = RuntimeError("some other error")

            with self.assertRaises(RuntimeError) as cm:
                main()

        self.assertEqual(str(cm.exception), "some other error")
        # Should not have slept for 15s (only 30s for sdk_token loop)
        calls = mock_sleep.call_args_list
        # If any sleep was called, it should be 30 (for sdk_token), not 15
        for c in calls:
            self.assertNotEqual(c[0][0], 15, f"Unexpected sleep(15) call: {c}")

    @patch("entrypoint.time.sleep")
    @patch("entrypoint.load_options")
    @patch("entrypoint.Path.exists")
    def test_entrypoint_skips_adapter_check_when_pairing_exists(
        self, mock_path_exists, mock_load_options, mock_sleep
    ):
        """When pairing.json exists, apply_ble_patches should NOT be called (adapter check skipped)."""
        from entrypoint import main

        mock_load_options.side_effect = [
            {"sdk_token": "mgst_test123"},
        ]
        # Path.exists for pairing.json returns True (already paired)
        # First call: OPTIONS_FILE.exists() in load_options()
        # Second call: PAIRING_FILE.exists() in main check
        mock_path_exists.side_effect = [True, True]

        with patch("ble_patch.apply_ble_patches") as mock_apply:
            main()

        # apply_ble_patches should NOT be called when pairing.json exists
        mock_apply.assert_not_called()
        # No sleep should be called
        mock_sleep.assert_not_called()

    @patch("entrypoint.time.sleep")
    @patch("entrypoint.load_options")
    @patch("entrypoint.PAIRING_FILE")
    @patch("entrypoint.OPTIONS_FILE")
    def test_entrypoint_skips_adapter_check_when_pairing_json_option_set(
        self, mock_options_file, mock_pairing_file, mock_load_options, mock_sleep
    ):
        """When pairing_json option is set and pairing.json doesn't exist yet,
        it gets imported and adapter check should be skipped."""
        from entrypoint import main

        mock_load_options.side_effect = [
            {"sdk_token": "mgst_test123", "pairing_json": '{"access_token": "test", "refresh_token": "test"}'},
        ]
        # Configure Path mocks for the specific file objects used in entrypoint.py
        mock_options_file.exists.return_value = True
        # PAIRING_FILE.exists() may be called multiple times:
        # 1. import check (line 77: if pairing_json_opt and not PAIRING_FILE.exists())
        # 2. main check (line 91: if not PAIRING_FILE.exists())
        # Add extra True values in case of additional calls
        mock_pairing_file.exists.side_effect = [False, True, True, True, True]

        with patch("ble_patch.apply_ble_patches") as mock_apply:
            with patch("entrypoint.open", return_value=None) as mock_open:
                with patch("entrypoint.json.dump"):
                    with patch("entrypoint.json.load", return_value={"access_token": "test", "refresh_token": "test"}):
                        main()

        # apply_ble_patches should NOT be called when pairing_json option is provided
        mock_apply.assert_not_called()


if __name__ == "__main__":
    unittest.main()