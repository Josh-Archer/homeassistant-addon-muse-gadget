"""Home Assistant Tool Bridge for Meta Muse Gadget SDK.

Injects native Home Assistant tools into COMMAND_SPECS and Executor,
and automatically introduces Home Assistant capabilities into the Meta Muse
chat upon connecting so Muse is immediately ready to control smart devices.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from musegadget.executor import COMMAND_SPECS, Executor, error, ok

log = logging.getLogger("musegadget.ha_bridge")


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

        node_id = getattr(session._device, "node_id", "homelink")
        announcement = (
            f"Home Assistant is online and connected via your Muse Gadget ({node_id})! "
            f"Found {count} smart entities{domain_str}. "
            "You can ask me to check device states, turn lights on or off, adjust thermostats, or trigger scenes."
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
    """Register Home Assistant tools in COMMAND_SPECS, hook Executor.run, and attach welcome hook."""

    COMMAND_SPECS["homeassistant.call_service"] = {
        "description": (
            "Call a service in Home Assistant to control smart devices (e.g. lights, "
            "switches, thermostats, media players, covers, locks, scenes, automations)."
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
                "description": "Parameters for the action, e.g. {'entity_id': 'light.living_room', 'brightness_pct': 80} or {'entity_id': 'climate.thermostat', 'temperature': 72}.",
            },
        },
        "timeout_ms": 15000,
    }

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

    COMMAND_SPECS["homeassistant.list_states"] = {
        "description": (
            "List entities and their current state in Home Assistant. "
            "Use the domain filter to view lights, switches, sensors, or climates."
        ),
        "optional": {
            "domain": {
                "type": "string",
                "description": "Optional filter domain, e.g. 'light', 'switch', 'climate', 'sensor', 'scene'.",
            },
        },
        "timeout_ms": 15000,
    }

    COMMAND_SPECS["homeassistant.render_template"] = {
        "description": "Evaluate a Jinja2 template in Home Assistant to query complex states.",
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
        if command == "homeassistant.call_service":
            domain = str(params.get("domain", "")).strip()
            service = str(params.get("service", "")).strip()
            service_data = params.get("service_data") or {}

            if not domain or not service:
                return error("Both 'domain' and 'service' are required.")

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
            states = ha_api_call("states", method="GET")

            if isinstance(states, dict) and "error" in states:
                return error(states["error"])

            if not isinstance(states, list):
                return error(f"Unexpected response from Home Assistant: {states}")

            if domain:
                domain_prefix = f"{domain.strip().lower()}."
                states = [s for s in states if s.get("entity_id", "").startswith(domain_prefix)]

            # Compact representation to prevent exceeding the 96 KiB frame limit
            summary = []
            for s in states:
                attrs = s.get("attributes", {})
                summary.append({
                    "entity_id": s.get("entity_id"),
                    "state": s.get("state"),
                    "friendly_name": attrs.get("friendly_name", s.get("entity_id")),
                    "unit": attrs.get("unit_of_measurement"),
                })

            return ok({
                "count": len(summary),
                "entities": summary[:120],  # safety ceiling
            })

        if command == "homeassistant.render_template":
            template_str = params.get("template", "")
            res = ha_api_call("template", method="POST", data={"template": template_str})
            if isinstance(res, dict) and "error" in res:
                return error(res["error"])
            return ok({"rendered": res})

        return original_run(self, command, params, timeout_ms)

    Executor.run = patched_run
    log.info("Installed Home Assistant tool handlers in Executor.")

    # Hook LinkSession to automatically introduce Home Assistant to Meta Muse upon registration
    try:
        from musegadget.link_client import LinkSession
        orig_handle = LinkSession._handle
        announced = set()

        def patched_handle(self: LinkSession, message: dict):
            outcome = orig_handle(self, message)
            if message.get("id") == self._register_id and message.get("method") is None and not message.get("error"):
                node_id = getattr(self._device, "node_id", "homelink")
                if node_id not in announced:
                    announced.add(node_id)
                    asyncio.create_task(_send_welcome_announcement(self))
            return outcome

        LinkSession._handle = patched_handle
        log.info("Installed Meta Muse automatic chat announcement hook.")
    except Exception as exc:
        log.warning("Could not install LinkSession announcement hook: %s", exc)
