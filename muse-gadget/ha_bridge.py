"""Home Assistant Tool Bridge for Meta Muse Gadget SDK (Phase 2).

Provides deep integration between Meta Muse and Home Assistant:
- Area & Room Intelligence: homeassistant.list_areas, homeassistant.get_area_devices
- Room-level service targeting: area_id & target support in homeassistant.call_service
- Smart pagination & area filtering in homeassistant.list_states
- Energy & Power Telemetry: homeassistant.get_energy
- Proactive notifications: homeassistant.notify_muse and built-in HTTP webhook on port 8099
- Automatic chat introduction upon connection
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

from musegadget.executor import COMMAND_SPECS, Executor, error, ok

log = logging.getLogger("musegadget.ha_bridge")

# Global reference to running event loop and active Service / LinkSession
_main_loop: asyncio.AbstractEventLoop | None = None
_current_service: Any = None
_active_session: Any = None

# In-memory area registry cache
_area_cache: list[dict] | None = None
_area_cache_time: float = 0.0
AREA_CACHE_TTL_S = 120.0


def ha_api_call(endpoint: str, method: str = "GET", data: dict | None = None) -> Any:
    """Execute an HTTP request against Home Assistant API."""
    ha_url = os.environ.get("HA_URL", "http://supervisor/core/api").rstrip("/")
    ha_token = os.environ.get("HA_TOKEN") or os.environ.get("SUPERVISOR_TOKEN", "")

    url = f"{ha_url}/{endpoint.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {ha_token}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        err_msg = exc.read().decode("utf-8", errors="replace")
        log.error("HA API HTTPError %d: %s", exc.code, err_msg)
        return {"error": f"Home Assistant HTTP {exc.code}: {err_msg}"}
    except Exception as exc:
        log.error("HA API request failed: %s", exc)
        return {"error": f"Failed to connect to Home Assistant: {exc}"}


def get_areas_registry(force_refresh: bool = False) -> list[dict]:
    """Retrieve all areas from Home Assistant with automatic caching.

    Uses Home Assistant's template rendering engine to query areas(), area_name(),
    and area_entities() safely without requiring WebSocket credentials.
    """
    global _area_cache, _area_cache_time
    now = time.monotonic()
    if not force_refresh and _area_cache is not None and (now - _area_cache_time) < AREA_CACHE_TTL_S:
        return _area_cache

    template = (
        '[{% for a in areas() %}'
        '{"area_id": {{ a | tojson }}, "name": {{ area_name(a) | tojson }}, '
        '"entities": {{ area_entities(a) | tojson }}}'
        '{% if not loop.last %},{% endif %}'
        '{% endfor %}]'
    )
    res = ha_api_call("template", method="POST", data={"template": template})
    if isinstance(res, str):
        try:
            parsed = json.loads(res)
            if isinstance(parsed, list):
                _area_cache = parsed
                _area_cache_time = now
                return parsed
        except Exception as exc:
            log.warning("Could not parse area template response: %s", exc)
    elif isinstance(res, list):
        _area_cache = res
        _area_cache_time = now
        return res

    return _area_cache or []


def resolve_area(area_query: str) -> dict | None:
    """Find an area by area_id or friendly name (case-insensitive with partial matching)."""
    if not area_query:
        return None
    q = area_query.strip().lower()

    areas = get_areas_registry()
    # 1. Exact match on area_id
    for a in areas:
        if str(a.get("area_id", "")).lower() == q:
            return a
    # 2. Exact match on friendly name
    for a in areas:
        if str(a.get("name", "")).lower() == q:
            return a
    # 3. Match normalized name (e.g. "living_room" vs "living room")
    q_norm = q.replace("_", " ")
    for a in areas:
        if str(a.get("name", "")).lower() == q_norm:
            return a
        if str(a.get("area_id", "")).lower() == q.replace(" ", "_"):
            return a
    # 4. Substring match
    for a in areas:
        if q in str(a.get("name", "")).lower() or q in str(a.get("area_id", "")).lower():
            return a

    # Refresh cache once if not matched
    areas = get_areas_registry(force_refresh=True)
    for a in areas:
        if str(a.get("area_id", "")).lower() == q or str(a.get("name", "")).lower() == q:
            return a
        if q in str(a.get("name", "")).lower() or q in str(a.get("area_id", "")).lower():
            return a

    return None


def query_energy_telemetry() -> dict:
    """Query energy, power, solar, and battery telemetry from Home Assistant."""
    states = ha_api_call("states", method="GET")
    if isinstance(states, dict) and "error" in states:
        return states
    if not isinstance(states, list):
        return {"error": f"Unexpected states response: {states}"}

    metrics = []
    power_terms = {"power", "energy", "solar", "battery", "consumption", "grid", "voltage", "current"}

    for s in states:
        eid = str(s.get("entity_id", ""))
        if not eid.startswith("sensor."):
            continue
        attrs = s.get("attributes", {})
        dclass = str(attrs.get("device_class", "")).lower()
        unit = str(attrs.get("unit_of_measurement", ""))

        is_telemetry = (
            dclass in {"power", "energy", "battery"}
            or unit in {"W", "kW", "kWh", "Wh", "MW", "MWh", "V", "A", "%"}
            or any(term in eid.lower() for term in power_terms)
        )

        if is_telemetry:
            metrics.append({
                "entity_id": eid,
                "friendly_name": attrs.get("friendly_name", eid),
                "state": s.get("state"),
                "unit": attrs.get("unit_of_measurement"),
                "device_class": attrs.get("device_class"),
            })

    # Sort prioritizing power/energy/battery classes
    def _sort_key(item: dict) -> int:
        dc = str(item.get("device_class", "")).lower()
        if dc == "power":
            return 0
        if dc == "energy":
            return 1
        if dc == "battery":
            return 2
        return 3

    metrics.sort(key=_sort_key)

    return {
        "count": len(metrics),
        "metrics": metrics[:60],  # Keep compact to fit well under 96 KiB
    }


async def notify_muse_chat(message: str) -> dict:
    """Send a proactive chat message to Meta Muse via the active session or local socket."""
    global _active_session, _current_service
    session = _active_session or (getattr(_current_service, "_current", None) if _current_service else None)

    if session is not None and getattr(session, "registered_at", None) is not None:
        try:
            res = await session.send_chat(message)
            return res if isinstance(res, dict) else {"ok": True, "result": res}
        except Exception as exc:
            log.warning("Direct session.send_chat failed: %s", exc)

    # Fallback: connect to local UNIX domain socket
    sock_path = os.environ.get("MUSE_SOCKET", "/run/musegadget/musegadget.sock")
    try:
        reader, writer = await asyncio.open_unix_connection(sock_path)
        writer.write(json.dumps({"message": message}).encode("utf-8") + b"\n")
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        writer.close()
        await writer.wait_closed()
        if line:
            return json.loads(line.decode("utf-8"))
    except Exception as exc:
        log.warning("UNIX socket send failed (%s): %s", sock_path, exc)

    return {"ok": False, "error": "Muse Gadget is not connected to Meta Muse cloud session"}


class NotifyHttpServer:
    """Lightweight async HTTP notification server for Home Assistant automations."""

    def __init__(self, port: int = 8099):
        self.port = port
        self.server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        try:
            self.server = await asyncio.start_server(self._handle_client, "0.0.0.0", self.port)
            log.info("Started Home Assistant Muse notification HTTP server on port %d", self.port)
        except Exception as exc:
            log.warning("Could not start notification HTTP server on port %d: %s", self.port, exc)

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            log.info("Stopped notification HTTP server.")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            req_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if not req_line:
                writer.close()
                return

            parts = req_line.decode("utf-8", errors="replace").split()
            if len(parts) < 2:
                writer.close()
                return
            method, path = parts[0].upper(), parts[1]

            # Read headers
            content_length = 0
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if not line or line in (b"\r\n", b"\n"):
                    break
                header_str = line.decode("utf-8", errors="replace")
                if ":" in header_str:
                    k, v = header_str.split(":", 1)
                    if k.strip().lower() == "content-length":
                        try:
                            content_length = int(v.strip())
                        except ValueError:
                            content_length = 0

            # GET /health or /status
            if method == "GET" and path in ("/health", "/status"):
                session = _active_session or (getattr(_current_service, "_current", None) if _current_service else None)
                connected = session is not None and getattr(session, "registered_at", None) is not None
                body = json.dumps({"status": "ok", "connected": connected, "version": "1.1.0"}).encode("utf-8")
                resp = (
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                    + str(len(body)).encode("ascii")
                    + b"\r\nConnection: close\r\n\r\n"
                    + body
                )
                writer.write(resp)
                await writer.drain()
                return

            # POST /notify
            if method == "POST" and path == "/notify":
                body_bytes = b""
                if content_length > 0:
                    body_bytes = await asyncio.wait_for(
                        reader.readexactly(min(content_length, 65536)), timeout=5.0
                    )
                try:
                    payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                except Exception:
                    payload = {}

                message = payload.get("message")
                if not message or not isinstance(message, str) or not message.strip():
                    err_body = json.dumps({"ok": False, "error": "Missing or empty 'message' in JSON body"}).encode("utf-8")
                    resp = (
                        b"HTTP/1.1 400 Bad Request\r\nContent-Type: application/json\r\nContent-Length: "
                        + str(len(err_body)).encode("ascii")
                        + b"\r\nConnection: close\r\n\r\n"
                        + err_body
                    )
                    writer.write(resp)
                    await writer.drain()
                    return

                res = await notify_muse_chat(message.strip())
                status_code = b"200 OK" if res.get("ok") else b"503 Service Unavailable"
                body = json.dumps(res).encode("utf-8")
                resp = (
                    b"HTTP/1.1 "
                    + status_code
                    + b"\r\nContent-Type: application/json\r\nContent-Length: "
                    + str(len(body)).encode("ascii")
                    + b"\r\nConnection: close\r\n\r\n"
                    + body
                )
                writer.write(resp)
                await writer.drain()
                return

            # 404 for unknown endpoints
            not_found = b'{"error": "Not Found"}'
            resp = (
                b"HTTP/1.1 404 Not Found\r\nContent-Type: application/json\r\nContent-Length: "
                + str(len(not_found)).encode("ascii")
                + b"\r\nConnection: close\r\n\r\n"
                + not_found
            )
            writer.write(resp)
            await writer.drain()
        except Exception as exc:
            log.warning("HTTP handler error: %s", exc)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


async def _send_welcome_announcement(session) -> None:
    """Send an introductory welcome message into the user's Meta Muse chat."""
    await asyncio.sleep(2.0)
    try:
        states = ha_api_call("states", method="GET")
        domains = set()
        count = 0
        if isinstance(states, list):
            count = len(states)
            for s in states:
                eid = s.get("entity_id", "")
                if "." in eid:
                    domains.add(eid.split(".", 1)[0])

        known = sorted(list(domains & {"light", "switch", "climate", "cover", "scene", "lock", "sensor", "media_player"}))
        domain_str = f" ({', '.join(known)})" if known else ""

        areas = get_areas_registry()
        area_count = len(areas)
        area_str = f" across {area_count} rooms" if area_count > 0 else ""

        node_id = getattr(session._device, "node_id", "homelink")
        announcement = (
            f"Home Assistant is online and connected via your Muse Gadget ({node_id})! "
            f"Found {count} smart entities{area_str}{domain_str}. "
            "You can ask me to check device states, control lights by room, adjust thermostats, or query home energy."
        )
        log.info("Sending Home Assistant welcome announcement to Meta Muse chat...")
        res = await session.send_chat(announcement)
        if res and res.get("ok"):
            log.info("Welcome announcement successfully delivered to Meta Muse chat!")
        else:
            log.info("Chat announcement response: %s", res)
    except Exception as exc:
        log.warning("Failed to deliver welcome announcement to Muse: %s", exc)


def install_ha_tools() -> None:
    """Register Home Assistant tools in COMMAND_SPECS, hook Executor.run, Service.run, and LinkSession."""

    # 1. homeassistant.call_service
    COMMAND_SPECS["homeassistant.call_service"] = {
        "description": (
            "Call a service in Home Assistant to control smart devices (e.g. lights, "
            "switches, thermostats, media players, covers, locks, scenes, automations). "
            "Supports targeting individual entities or entire rooms/areas."
        ),
        "required": {
            "domain": {
                "type": "string",
                "description": "Integration domain, e.g. 'light', 'switch', 'climate', 'cover', 'media_player', 'scene', 'automation'.",
            },
            "service": {
                "type": "string",
                "description": "Action name, e.g. 'turn_on', 'turn_off', 'toggle', 'set_temperature', 'open_cover', 'trigger'.",
            },
        },
        "optional": {
            "service_data": {
                "type": "object",
                "description": "Parameters for the action, e.g. {'brightness_pct': 80} or {'temperature': 72}.",
            },
            "area_id": {
                "type": "string",
                "description": "Target an entire room by area name or ID (e.g. 'living_room' or 'Living Room').",
            },
            "entity_id": {
                "type": "string",
                "description": "Target a specific device by entity ID (e.g. 'light.kitchen').",
            },
            "target": {
                "type": "object",
                "description": "Target object, e.g. {'area_id': 'living_room'} or {'entity_id': 'light.kitchen'}.",
            },
        },
        "timeout_ms": 15000,
    }

    # 2. homeassistant.get_state
    COMMAND_SPECS["homeassistant.get_state"] = {
        "description": "Fetch the current state and attributes of a specific Home Assistant entity.",
        "required": {
            "entity_id": {
                "type": "string",
                "description": "Entity ID, e.g. 'light.living_room', 'climate.thermostat', 'sensor.indoor_temperature'.",
            },
        },
        "timeout_ms": 10000,
    }

    # 3. homeassistant.list_states
    COMMAND_SPECS["homeassistant.list_states"] = {
        "description": (
            "List entities and their current state in Home Assistant. "
            "Supports filtering by domain or area/room, and includes pagination to support large homes."
        ),
        "optional": {
            "domain": {
                "type": "string",
                "description": "Filter domain, e.g. 'light', 'switch', 'climate', 'sensor', 'scene'.",
            },
            "area": {
                "type": "string",
                "description": "Filter by room or area name or ID (e.g. 'living_room', 'Kitchen').",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of entities to return per page (1-100, default 50).",
            },
            "offset": {
                "type": "integer",
                "description": "Zero-based pagination offset (default 0).",
            },
        },
        "timeout_ms": 15000,
    }

    # 4. homeassistant.list_areas
    COMMAND_SPECS["homeassistant.list_areas"] = {
        "description": (
            "List all configured rooms and areas in Home Assistant, including their area ID, "
            "friendly name, and count of associated smart devices."
        ),
        "optional": {},
        "timeout_ms": 10000,
    }

    # 5. homeassistant.get_area_devices
    COMMAND_SPECS["homeassistant.get_area_devices"] = {
        "description": (
            "Get all smart devices and entities located in a specific room or area in Home Assistant. "
            "Allows inspecting everything in a room (lights, thermostats, sensors, etc.)."
        ),
        "required": {
            "area": {
                "type": "string",
                "description": "Area name or ID, e.g. 'Living Room', 'kitchen', 'master_bedroom'.",
            },
        },
        "optional": {
            "domain": {
                "type": "string",
                "description": "Optional domain filter, e.g. 'light', 'climate', 'switch', 'sensor'.",
            },
        },
        "timeout_ms": 15000,
    }

    # 6. homeassistant.get_energy
    COMMAND_SPECS["homeassistant.get_energy"] = {
        "description": (
            "Query Home Assistant Energy and Power telemetry (solar production, grid consumption, "
            "battery storage, and major power loads)."
        ),
        "optional": {
            "domain": {
                "type": "string",
                "description": "Optional filter domain, defaults to 'sensor'.",
            },
        },
        "timeout_ms": 10000,
    }

    # 7. homeassistant.notify_muse
    COMMAND_SPECS["homeassistant.notify_muse"] = {
        "description": "Send a chat notification or proactive alert directly to the user's Meta Muse chat.",
        "required": {
            "message": {
                "type": "string",
                "description": "The message text to send to Meta Muse.",
            },
        },
        "timeout_ms": 10000,
    }

    # 8. homeassistant.render_template
    COMMAND_SPECS["homeassistant.render_template"] = {
        "description": "Evaluate a Jinja2 template in Home Assistant to query complex states or calculations.",
        "required": {
            "template": {
                "type": "string",
                "description": "Jinja2 template string, e.g. \"{{ states('sensor.outside_temperature') }}\".",
            },
        },
        "timeout_ms": 10000,
    }

    original_run = Executor.run

    def patched_run(self: Executor, command: str, params: dict, timeout_ms: int | None = None) -> dict:
        global _main_loop, _active_session, _current_service

        if command == "homeassistant.call_service":
            domain = str(params.get("domain", "")).strip()
            service = str(params.get("service", "")).strip()
            service_data = dict(params.get("service_data") or {})

            if not domain or not service:
                return error("Both 'domain' and 'service' are required.")

            # Target resolution for room-level control
            raw_area = params.get("area_id") or service_data.get("area_id")
            if raw_area:
                resolved = resolve_area(str(raw_area))
                area_id = resolved["area_id"] if resolved else str(raw_area)
                if "target" in params and isinstance(params["target"], dict):
                    service_data["target"] = {**params["target"], "area_id": area_id}
                else:
                    service_data["target"] = {"area_id": area_id}
                service_data["area_id"] = area_id

            entity_id = params.get("entity_id")
            if entity_id and "entity_id" not in service_data:
                if "target" in service_data and isinstance(service_data["target"], dict):
                    service_data["target"]["entity_id"] = entity_id
                else:
                    service_data["entity_id"] = entity_id

            if "target" in params and isinstance(params["target"], dict):
                service_data["target"] = {**service_data.get("target", {}), **params["target"]}

            res = ha_api_call(f"services/{domain}/{service}", method="POST", data=service_data)
            if isinstance(res, dict) and "error" in res:
                return error(res["error"])
            return ok({"success": True, "result": res})

        if command == "homeassistant.get_state":
            entity_id = str(params.get("entity_id", "")).strip()
            if not entity_id:
                return error("'entity_id' is required.")

            res = ha_api_call(f"states/{entity_id}", method="GET")
            if isinstance(res, dict) and "error" in res:
                return error(res["error"])
            return ok({"entity": res})

        if command == "homeassistant.list_states":
            domain = params.get("domain")
            area = params.get("area")
            try:
                limit = min(max(int(params.get("limit", 50)), 1), 100)
            except (ValueError, TypeError):
                limit = 50
            try:
                offset = max(int(params.get("offset", 0)), 0)
            except (ValueError, TypeError):
                offset = 0

            states = ha_api_call("states", method="GET")
            if isinstance(states, dict) and "error" in states:
                return error(states["error"])
            if not isinstance(states, list):
                return error(f"Unexpected response from Home Assistant: {states}")

            # Filter by area if requested
            if area:
                resolved = resolve_area(str(area))
                if resolved:
                    allowed_entities = set(resolved.get("entities", []))
                    states = [s for s in states if s.get("entity_id") in allowed_entities]
                else:
                    return ok({
                        "count": 0,
                        "total": 0,
                        "offset": offset,
                        "limit": limit,
                        "has_more": False,
                        "entities": [],
                        "warning": f"Area '{area}' not found in Home Assistant.",
                    })

            # Filter by domain if requested
            if domain:
                domain_prefix = f"{str(domain).strip().lower()}."
                states = [s for s in states if s.get("entity_id", "").startswith(domain_prefix)]

            total = len(states)
            paged_states = states[offset : offset + limit]

            # Compact representation to keep payload safely within Noise limits
            summary = []
            for s in paged_states:
                attrs = s.get("attributes", {})
                summary.append({
                    "entity_id": s.get("entity_id"),
                    "state": s.get("state"),
                    "friendly_name": attrs.get("friendly_name", s.get("entity_id")),
                    "unit": attrs.get("unit_of_measurement"),
                })

            return ok({
                "count": len(summary),
                "total": total,
                "offset": offset,
                "limit": limit,
                "has_more": (offset + len(summary)) < total,
                "entities": summary,
            })

        if command == "homeassistant.list_areas":
            areas = get_areas_registry()
            summary = [
                {
                    "area_id": a.get("area_id"),
                    "name": a.get("name"),
                    "entity_count": len(a.get("entities", [])),
                }
                for a in areas
            ]
            return ok({"count": len(summary), "areas": summary})

        if command == "homeassistant.get_area_devices":
            area_query = str(params.get("area", "")).strip()
            domain_filter = params.get("domain")
            if not area_query:
                return error("'area' is required.")

            resolved = resolve_area(area_query)
            if not resolved:
                return error(f"Area '{area_query}' was not found in Home Assistant.")

            entity_ids = set(resolved.get("entities", []))
            if domain_filter:
                d_prefix = f"{str(domain_filter).strip().lower()}."
                entity_ids = {e for e in entity_ids if e.startswith(d_prefix)}

            states = ha_api_call("states", method="GET")
            if isinstance(states, dict) and "error" in states:
                return error(states["error"])
            if not isinstance(states, list):
                return error(f"Unexpected response from Home Assistant: {states}")

            items = []
            for s in states:
                eid = s.get("entity_id", "")
                if eid in entity_ids:
                    attrs = s.get("attributes", {})
                    items.append({
                        "entity_id": eid,
                        "friendly_name": attrs.get("friendly_name", eid),
                        "state": s.get("state"),
                        "domain": eid.split(".", 1)[0] if "." in eid else "",
                        "device_class": attrs.get("device_class"),
                        "unit": attrs.get("unit_of_measurement"),
                    })

            return ok({
                "area_id": resolved.get("area_id"),
                "area_name": resolved.get("name"),
                "count": len(items),
                "entities": items,
            })

        if command == "homeassistant.get_energy":
            telemetry = query_energy_telemetry()
            if isinstance(telemetry, dict) and "error" in telemetry:
                return error(telemetry["error"])
            return ok(telemetry)

        if command == "homeassistant.notify_muse":
            message = str(params.get("message", "")).strip()
            if not message:
                return error("'message' is required.")

            session = _active_session or (getattr(_current_service, "_current", None) if _current_service else None)
            if session is None or getattr(session, "registered_at", None) is None:
                return error("Muse Gadget is not currently connected to Meta Muse cloud session.")

            loop = _main_loop
            if loop and loop.is_running():
                try:
                    fut = asyncio.run_coroutine_threadsafe(session.send_chat(message), loop)
                    res = fut.result(timeout=10.0)
                    return ok({"delivered": True, "result": res})
                except Exception as exc:
                    return error(f"Failed to deliver notification to Meta Muse: {exc}")
            else:
                return error("Internal event loop is not active.")

        if command == "homeassistant.render_template":
            template_str = params.get("template", "")
            res = ha_api_call("template", method="POST", data={"template": template_str})
            if isinstance(res, dict) and "error" in res:
                return error(res["error"])
            return ok({"rendered": res})

        return original_run(self, command, params, timeout_ms)

    Executor.run = patched_run
    log.info("Installed Home Assistant Phase 2 tool handlers in Executor.")

    # Hook LinkSession to capture active session and deliver welcome announcement
    try:
        from musegadget.link_client import LinkSession

        orig_handle = LinkSession._handle
        announced = set()

        def patched_handle(self: LinkSession, message: dict):
            global _active_session
            _active_session = self
            outcome = orig_handle(self, message)
            if message.get("id") == self._register_id and message.get("method") is None and not message.get("error"):
                node_id = getattr(self._device, "node_id", "homelink")
                if node_id not in announced:
                    announced.add(node_id)
                    asyncio.create_task(_send_welcome_announcement(self))
            return outcome

        LinkSession._handle = patched_handle
        log.info("Installed Meta Muse session and chat announcement hook.")
    except Exception as exc:
        log.warning("Could not install LinkSession hook: %s", exc)

    # Hook Service.run to run the notification HTTP server alongside the daemon
    try:
        from musegadget.service import Service

        orig_service_run = Service.run

        async def patched_service_run(self: Service):
            global _current_service, _main_loop
            _current_service = self
            _main_loop = asyncio.get_running_loop()

            port = int(os.environ.get("MUSE_NOTIFY_PORT", "8099"))
            http_server = NotifyHttpServer(port=port)
            await http_server.start()
            try:
                return await orig_service_run(self)
            finally:
                await http_server.stop()

        Service.run = patched_service_run
        log.info("Installed Service notification HTTP server hook.")
    except Exception as exc:
        log.warning("Could not install Service hook: %s", exc)
