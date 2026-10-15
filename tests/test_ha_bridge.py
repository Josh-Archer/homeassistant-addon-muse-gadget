"""Unit tests for Phase 2 Home Assistant Tool Bridge and Notification Server."""

from __future__ import annotations

import asyncio
import io
import json
import sys
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure muse-gadget directory is on sys.path dynamically
app_dir = Path(__file__).resolve().parent.parent / "muse-gadget"
if app_dir.exists():
    sys.path.insert(0, str(app_dir))
if Path("/app").exists():
    sys.path.insert(0, "/app")
if Path("/tmp/muse-gadget-sdk/linux/src").exists():
    sys.path.insert(0, "/tmp/muse-gadget-sdk/linux/src")

import ha_bridge
from musegadget.executor import COMMAND_SPECS, Executor


def make_http_response(body: bytes, status: int = 200, headers: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = body
    resp.status = status
    resp.headers = headers or {}
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = None
    return resp


class TestHaBridgePhase2(unittest.TestCase):
    def setUp(self):
        # Reset cache before each test
        ha_bridge._area_cache = None
        ha_bridge._area_cache_time = 0.0
        ha_bridge._active_session = None
        ha_bridge._current_service = None
        ha_bridge.install_ha_tools()
        self.executor = Executor(MagicMock(uid=1000, gid=1000, name="muse"))

    def test_command_specs_registered(self):
        """Verify all Phase 2 tools are registered with schemas in COMMAND_SPECS."""
        expected_tools = [
            "homeassistant.call_service",
            "homeassistant.get_state",
            "homeassistant.list_states",
            "homeassistant.list_areas",
            "homeassistant.get_area_devices",
            "homeassistant.get_energy",
            "homeassistant.notify_muse",
            "homeassistant.render_template",
        ]
        for tool in expected_tools:
            self.assertIn(tool, COMMAND_SPECS, f"Tool {tool} must be in COMMAND_SPECS")

    @patch("ha_bridge.ha_api_call")
    def test_list_areas(self, mock_api):
        """Verify homeassistant.list_areas returns area metadata."""
        mock_api.return_value = [
            {"area_id": "living_room", "name": "Living Room", "entities": ["light.living_room_1", "switch.fan"]},
            {"area_id": "kitchen", "name": "Kitchen", "entities": ["light.kitchen"]},
        ]
        res = self.executor.run("homeassistant.list_areas", {})
        self.assertTrue(res.get("ok"))
        out = res.get("payload", {})
        self.assertEqual(out.get("count"), 2)
        self.assertEqual(out["areas"][0]["area_id"], "living_room")
        self.assertEqual(out["areas"][0]["name"], "Living Room")
        self.assertEqual(out["areas"][0]["entity_count"], 2)

    @patch("ha_bridge.ha_api_call")
    def test_get_area_devices(self, mock_api):
        """Verify homeassistant.get_area_devices resolves room and filters entities."""
        def side_effect(endpoint, method="GET", data=None):
            if endpoint == "template":
                return [
                    {"area_id": "living_room", "name": "Living Room", "entities": ["light.lr_main", "sensor.lr_temp"]},
                ]
            if endpoint == "states":
                return [
                    {"entity_id": "light.lr_main", "state": "on", "attributes": {"friendly_name": "Living Room Light"}},
                    {"entity_id": "sensor.lr_temp", "state": "72.4", "attributes": {"unit_of_measurement": "°F", "device_class": "temperature"}},
                    {"entity_id": "light.bedroom", "state": "off", "attributes": {}},
                ]
            return {}

        mock_api.side_effect = side_effect

        # Query by friendly name
        res = self.executor.run("homeassistant.get_area_devices", {"area": "living room"})
        self.assertTrue(res.get("ok"))
        out = res.get("payload", {})
        self.assertEqual(out.get("area_id"), "living_room")
        self.assertEqual(out.get("count"), 2)
        entity_ids = [e["entity_id"] for e in out.get("entities", [])]
        self.assertIn("light.lr_main", entity_ids)
        self.assertIn("sensor.lr_temp", entity_ids)
        self.assertNotIn("light.bedroom", entity_ids)

        # Query with domain filter
        res_filtered = self.executor.run("homeassistant.get_area_devices", {"area": "Living Room", "domain": "light"})
        out_filtered = res_filtered.get("payload", {})
        self.assertEqual(out_filtered.get("count"), 1)
        self.assertEqual(out_filtered["entities"][0]["entity_id"], "light.lr_main")

    @patch("ha_bridge.ha_api_call")
    def test_call_service_with_area_target(self, mock_api):
        """Verify homeassistant.call_service properly constructs area targets."""
        ha_bridge._area_cache = [{"area_id": "living_room", "name": "Living Room", "entities": []}]
        ha_bridge._area_cache_time = time.monotonic()
        mock_api.return_value = [{"entity_id": "light.living_room_1"}]

        res = self.executor.run("homeassistant.call_service", {
            "domain": "light",
            "service": "turn_off",
            "area_id": "Living Room",
        })
        self.assertTrue(res.get("ok"))
        mock_api.assert_called_with(
            "services/light/turn_off",
            method="POST",
            data={"target": {"area_id": "living_room"}, "area_id": "living_room"},
        )

    @patch("ha_bridge.ha_api_call")
    def test_list_states_pagination_and_area_filter(self, mock_api):
        """Verify pagination (limit/offset/has_more) and area filtering in list_states."""
        ha_bridge._area_cache = [
            {"area_id": "kitchen", "name": "Kitchen", "entities": ["light.k1", "light.k2", "switch.coffee"]},
        ]
        ha_bridge._area_cache_time = time.monotonic()
        all_states = [
            {"entity_id": f"light.item_{i}", "state": "off", "attributes": {"friendly_name": f"Item {i}"}}
            for i in range(120)
        ] + [
            {"entity_id": "light.k1", "state": "on", "attributes": {"friendly_name": "Kitchen 1"}},
            {"entity_id": "light.k2", "state": "off", "attributes": {"friendly_name": "Kitchen 2"}},
            {"entity_id": "switch.coffee", "state": "off", "attributes": {"friendly_name": "Coffee Maker"}},
        ]
        mock_api.return_value = all_states

        # 1. Test pagination on all states (limit 50, offset 0)
        res = self.executor.run("homeassistant.list_states", {"limit": 50, "offset": 0})
        self.assertTrue(res.get("ok"))
        out = res.get("payload", {})
        self.assertEqual(out.get("total"), 123)
        self.assertEqual(out.get("count"), 50)
        self.assertEqual(out.get("offset"), 0)
        self.assertTrue(out.get("has_more"))

        # 2. Test pagination offset (limit 50, offset 100)
        res2 = self.executor.run("homeassistant.list_states", {"limit": 50, "offset": 100})
        out2 = res2.get("payload", {})
        self.assertEqual(out2.get("count"), 23)
        self.assertFalse(out2.get("has_more"))

        # 3. Test area filter
        res_area = self.executor.run("homeassistant.list_states", {"area": "Kitchen"})
        out_area = res_area.get("payload", {})
        self.assertEqual(out_area.get("total"), 3)
        self.assertEqual(out_area.get("count"), 3)
        self.assertFalse(out_area.get("has_more"))

    @patch("ha_bridge.ha_api_call")
    def test_get_energy_telemetry(self, mock_api):
        """Verify homeassistant.get_energy extracts energy and power telemetry."""
        mock_api.return_value = [
            {"entity_id": "sensor.grid_power", "state": "1250", "attributes": {"unit_of_measurement": "W", "device_class": "power", "friendly_name": "Grid Power"}},
            {"entity_id": "sensor.solar_inverter", "state": "3400", "attributes": {"unit_of_measurement": "W", "device_class": "power", "friendly_name": "Solar"}},
            {"entity_id": "sensor.battery_soc", "state": "85", "attributes": {"unit_of_measurement": "%", "device_class": "battery", "friendly_name": "Battery Level"}},
            {"entity_id": "sensor.weather_temp", "state": "70", "attributes": {"unit_of_measurement": "°F", "device_class": "temperature"}},
        ]
        res = self.executor.run("homeassistant.get_energy", {})
        self.assertTrue(res.get("ok"))
        out = res.get("payload", {})
        self.assertEqual(out.get("count"), 3)
        entity_ids = [m["entity_id"] for m in out.get("metrics", [])]
        self.assertIn("sensor.grid_power", entity_ids)
        self.assertIn("sensor.solar_inverter", entity_ids)
        self.assertIn("sensor.battery_soc", entity_ids)
        self.assertNotIn("sensor.weather_temp", entity_ids)

    @patch("urllib.request.urlopen")
    def test_ha_api_call_template_plain_text_on(self, mock_urlopen):
        """Verify template endpoint returns unchanged plain text 'on'."""
        mock_urlopen.return_value = make_http_response(b"on")
        raw_res = ha_bridge.ha_api_call("template", method="POST", data={"template": "{{ 'on' }}"})
        self.assertEqual(raw_res, "on")
        self.assertIsInstance(raw_res, str)

        cmd_res = self.executor.run("homeassistant.render_template", {"template": "{{ 'on' }}"})
        self.assertTrue(cmd_res.get("ok"))
        rendered = cmd_res.get("payload", {}).get("rendered")
        self.assertEqual(rendered, "on")
        self.assertIsInstance(rendered, str)

    @patch("urllib.request.urlopen")
    def test_ha_api_call_template_plain_text_prose(self, mock_urlopen):
        """Verify template endpoint returns unchanged arbitrary prose."""
        prose = "It is Tuesday!"
        mock_urlopen.return_value = make_http_response(prose.encode("utf-8"))
        raw_res = ha_bridge.ha_api_call("template", method="POST", data={"template": prose})
        self.assertEqual(raw_res, prose)
        self.assertIsInstance(raw_res, str)

        cmd_res = self.executor.run("homeassistant.render_template", {"template": prose})
        self.assertTrue(cmd_res.get("ok"))
        rendered = cmd_res.get("payload", {}).get("rendered")
        self.assertEqual(rendered, prose)
        self.assertIsInstance(rendered, str)

    @patch("urllib.request.urlopen")
    def test_ha_api_call_template_plain_text_number(self, mock_urlopen):
        """Verify template endpoint returns numeric string unchanged as text, not float."""
        mock_urlopen.return_value = make_http_response(b"23.5")
        raw_res = ha_bridge.ha_api_call("template", method="POST", data={"template": "23.5"})
        self.assertEqual(raw_res, "23.5")
        self.assertIsInstance(raw_res, str)
        self.assertNotIsInstance(raw_res, float)

        cmd_res = self.executor.run("homeassistant.render_template", {"template": "23.5"})
        self.assertTrue(cmd_res.get("ok"))
        rendered = cmd_res.get("payload", {}).get("rendered")
        self.assertEqual(rendered, "23.5")
        self.assertIsInstance(rendered, str)
        self.assertNotIsInstance(rendered, float)

    @patch("urllib.request.urlopen")
    def test_ha_api_call_template_http_error(self, mock_urlopen):
        """Verify HTTP errors in template rendering return structured error dictionaries."""
        def make_http_error(*args, **kwargs):
            raise urllib.error.HTTPError(
                url="http://supervisor/core/api/template",
                code=400,
                msg="Bad Request",
                hdrs={},
                fp=io.BytesIO(b"Template syntax error: unexpected end of template"),
            )
        mock_urlopen.side_effect = make_http_error
        raw_res = ha_bridge.ha_api_call("template", method="POST", data={"template": "{{ invalid"})
        self.assertIsInstance(raw_res, dict)
        self.assertIn("error", raw_res)
        self.assertIn("Home Assistant HTTP 400: Template syntax error", raw_res["error"])

        cmd_res = self.executor.run("homeassistant.render_template", {"template": "{{ invalid"})
        self.assertFalse(cmd_res.get("ok"))
        self.assertIn("Home Assistant HTTP 400: Template syntax error", cmd_res.get("error", ""))

    @patch("urllib.request.urlopen")
    def test_ha_api_call_non_template_json_decoding(self, mock_urlopen):
        """Verify non-template API endpoints continue to be JSON-decoded."""
        mock_urlopen.return_value = make_http_response(b'{"entity_id": "light.kitchen", "state": "on"}')
        raw_res = ha_bridge.ha_api_call("states/light.kitchen", method="GET")
        self.assertIsInstance(raw_res, dict)
        self.assertEqual(raw_res.get("state"), "on")

    @patch("urllib.request.urlopen")
    def test_area_discovery_explicit_json_decode_through_http_helper(self, mock_urlopen):
        """Verify area discovery callers explicitly JSON-decode their template responses."""
        areas_payload = [
            {"area_id": "living_room", "name": "Living Room", "entities": ["light.living_room_1", "switch.fan"]},
            {"area_id": "kitchen", "name": "Kitchen", "entities": ["light.kitchen"]},
        ]
        mock_urlopen.return_value = make_http_response(json.dumps(areas_payload).encode("utf-8"))

        areas = ha_bridge.get_areas_registry(force_refresh=True)
        self.assertIsInstance(areas, list)
        self.assertEqual(len(areas), 2)
        self.assertEqual(areas[0]["area_id"], "living_room")

        ha_bridge._area_cache = None
        ha_bridge._area_cache_time = 0.0
        res = self.executor.run("homeassistant.list_areas", {})
        self.assertTrue(res.get("ok"))
        out = res.get("payload", {})
        self.assertEqual(out.get("count"), 2)
        self.assertEqual(out["areas"][0]["area_id"], "living_room")
        self.assertEqual(out["areas"][0]["entity_count"], 2)

    @patch("urllib.request.urlopen")
    def test_get_area_devices_through_http_helper(self, mock_urlopen):
        """Verify homeassistant.get_area_devices explicitly decodes area template via HTTP helper."""
        def fake_urlopen(req, timeout=15):
            url = req.full_url
            if "template" in url:
                return make_http_response(json.dumps([
                    {"area_id": "living_room", "name": "Living Room", "entities": ["light.lr_main", "sensor.lr_temp"]},
                ]).encode("utf-8"))
            if "states" in url:
                return make_http_response(json.dumps([
                    {"entity_id": "light.lr_main", "state": "on", "attributes": {"friendly_name": "Living Room Light"}},
                    {"entity_id": "sensor.lr_temp", "state": "72.4", "attributes": {"unit_of_measurement": "\u00b0F", "device_class": "temperature"}},
                ]).encode("utf-8"))
            return make_http_response(b"{}")

        mock_urlopen.side_effect = fake_urlopen
        res = self.executor.run("homeassistant.get_area_devices", {"area": "living_room"})
        self.assertTrue(res.get("ok"))
        out = res.get("payload", {})
        self.assertEqual(out.get("area_id"), "living_room")
        self.assertEqual(out.get("count"), 2)
        entity_ids = [e["entity_id"] for e in out.get("entities", [])]
        self.assertIn("light.lr_main", entity_ids)
        self.assertIn("sensor.lr_temp", entity_ids)

    @patch("urllib.request.urlopen")
    def test_area_discovery_http_error_falls_back_gracefully(self, mock_urlopen):
        """Verify area discovery gracefully handles HTTP errors when template endpoint fails."""
        err = urllib.error.HTTPError(
            url="http://supervisor/core/api/template",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=io.BytesIO(b"Internal Server Error"),
        )
        mock_urlopen.side_effect = err
        areas = ha_bridge.get_areas_registry(force_refresh=True)
        self.assertEqual(areas, [])


class TestHttpNotificationServer(unittest.IsolatedAsyncioTestCase):
    async def test_notify_http_server(self):
        """Verify the built-in HTTP server responds to /health and /notify."""
        server = ha_bridge.NotifyHttpServer(port=8199)
        await server.start()
        try:
            # Test /health
            reader, writer = await asyncio.open_connection("127.0.0.1", 8199)
            writer.write(b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
            await writer.drain()
            resp_bytes = await reader.read(1024)
            writer.close()
            await writer.wait_closed()
            self.assertIn(b"200 OK", resp_bytes)
            self.assertIn(b'"version": "1.1.0"', resp_bytes)

            # Test /notify validation with empty message
            reader2, writer2 = await asyncio.open_connection("127.0.0.1", 8199)
            payload = json.dumps({"message": ""}).encode("utf-8")
            writer2.write(
                b"POST /notify HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: "
                + str(len(payload)).encode()
                + b"\r\n\r\n"
                + payload
            )
            await writer2.drain()
            resp2_bytes = await reader2.read(1024)
            writer2.close()
            await writer2.wait_closed()
            self.assertIn(b"400 Bad Request", resp2_bytes)

            # Test /notify with valid message when not connected
            reader3, writer3 = await asyncio.open_connection("127.0.0.1", 8199)
            payload3 = json.dumps({"message": "Garage door opened"}).encode("utf-8")
            writer3.write(
                b"POST /notify HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: "
                + str(len(payload3)).encode()
                + b"\r\n\r\n"
                + payload3
            )
            await writer3.drain()
            resp3_bytes = await reader3.read(1024)
            writer3.close()
            await writer3.wait_closed()
            self.assertIn(b"503 Service Unavailable", resp3_bytes)

        finally:
            await server.stop()


if __name__ == "__main__":
    unittest.main()
