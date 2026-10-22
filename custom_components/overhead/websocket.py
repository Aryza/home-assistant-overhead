"""Authenticated entry-scoped snapshots and administrator artwork commands."""

import logging
import probatio as vol
from homeassistant.components import websocket_api
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def handle(hass, connection, msg):
    """Common dispatch kept separate for actual-framework tests."""
    if not connection.user:
        connection.send_error(msg["id"], "unauthorized", "Sign in to Home Assistant")
        return
    entries = hass.data[DOMAIN]["entries"]
    kind = msg["type"].split("/")[-1]
    if kind == "entries":
        connection.send_result(
            msg["id"],
            [
                {"entry_id": key, "name": c.engine.settings["name"]}
                for key, c in entries.items()
            ],
        )
        return
    coordinator = entries.get(msg.get("entry_id"))
    if coordinator is None:
        connection.send_error(
            msg["id"], "not_found", "Overhead integration entry is not loaded"
        )
        return
    engine = coordinator.engine
    try:
        if kind == "snapshot":
            result = await hass.async_add_executor_job(
                engine.snapshot,
                msg["profile_id"],
                msg.get("options", {}),
                msg.get("preview", True),
                connection.user.is_admin,
            )
        elif kind == "metadata":
            result = await hass.async_add_executor_job(engine.metadata)
        elif kind == "manage":
            action = msg.get("action", "status")
            if action != "status" and not connection.user.is_admin:
                connection.send_error(
                    msg["id"],
                    "unauthorized",
                    "An administrator is required for artwork changes",
                )
                return
            result = await hass.async_add_executor_job(
                engine.manage, action, msg.get("key", ""), msg.get("version", 0)
            )
        else:
            raise ValueError("Unknown command")
        connection.send_result(msg["id"], result)
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_request", str(exc))
    except Exception:
        _LOGGER.exception("Overhead request failed")
        connection.send_error(
            msg["id"],
            "request_failed",
            "Overhead could not complete the request; see the Home Assistant log",
        )


@websocket_api.websocket_command({vol.Required("type"): "overhead/entries"})
@websocket_api.async_response
async def ws_entries(hass, connection, msg):
    await handle(hass, connection, msg)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "overhead/snapshot",
        vol.Required("entry_id"): str,
        vol.Required("profile_id"): str,
        vol.Optional("options", default={}): dict,
        vol.Optional("preview", default=True): bool,
    }
)
@websocket_api.async_response
async def ws_snapshot(hass, connection, msg):
    await handle(hass, connection, msg)


@websocket_api.websocket_command(
    {vol.Required("type"): "overhead/metadata", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def ws_metadata(hass, connection, msg):
    await handle(hass, connection, msg)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "overhead/manage",
        vol.Required("entry_id"): str,
        vol.Optional("action", default="status"): vol.In(
            [
                "status",
                "paint",
                "repaint",
                "restore",
                "delete",
                "purge",
                "remove_profile",
            ]
        ),
        vol.Optional("key", default=""): str,
        vol.Optional("version", default=0): vol.All(int, vol.Range(min=0)),
    }
)
@websocket_api.async_response
async def ws_manage(hass, connection, msg):
    await handle(hass, connection, msg)


def register(hass):
    for command in (ws_entries, ws_snapshot, ws_metadata, ws_manage):
        websocket_api.async_register_command(hass, command)
