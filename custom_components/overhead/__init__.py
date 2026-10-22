"""Overhead aircraft dashboards, adapted from Tesserae Overhead."""

from pathlib import Path
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from .const import DOMAIN
from .coordinator import OverheadCoordinator
from .engine import Engine
from .websocket import register


async def async_setup(hass, config):
    hass.data.setdefault(DOMAIN, {"entries": {}})
    register(hass)
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                "/overhead-static", str(Path(__file__).parent / "frontend"), False
            )
        ]
    )
    return True


async def async_setup_entry(hass, entry):
    settings = {**entry.data, **entry.options, "timezone": hass.config.time_zone}
    folder = Path(hass.config.path(".storage", "overhead", entry.entry_id))
    engine = await hass.async_add_executor_job(Engine, folder, settings)
    coordinator = OverheadCoordinator(hass, entry, engine)
    try:
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        hass.data[DOMAIN]["entries"][entry.entry_id] = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    except Exception:
        hass.data[DOMAIN]["entries"].pop(entry.entry_id, None)
        await coordinator.async_shutdown()
        await hass.async_add_executor_job(engine.close)
        raise

    async def stop(_event):
        await coordinator.async_shutdown()
        await hass.async_add_executor_job(engine.close)

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop))
    return True


async def async_unload_entry(hass, entry):
    if not await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR]):
        return False
    coordinator = hass.data[DOMAIN]["entries"].pop(entry.entry_id)
    await coordinator.async_shutdown()
    await hass.async_add_executor_job(coordinator.engine.close)
    return True
