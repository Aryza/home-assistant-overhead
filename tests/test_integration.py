from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from homeassistant.core import HomeAssistant


@pytest.mark.asyncio
async def test_config_flow_defaults_and_creation(tmp_path):
    from overhead_test.config_flow import OverheadConfigFlow

    hass = HomeAssistant(str(tmp_path))
    flow = OverheadConfigFlow()
    flow.hass = hass
    result = await flow.async_step_user()
    schema = result["data_schema"]
    values = schema(
        {
            "name": "Garden",
            "latitude": 52.0,
            "longitude": 13.0,
            "radius_km": "25",
            "source": "adsb_lol",
        }
    )
    result = await flow.async_step_user(values)
    assert result["type"] == "create_entry"
    assert result["data"]["generation_enabled"] is False
    assert result["data"]["latitude"] == 52.0
    await hass.async_stop()


@pytest.mark.asyncio
async def test_api_admin_restriction_and_entry_selection(tmp_path):
    from overhead_test.websocket import handle

    hass = HomeAssistant(str(tmp_path))
    engine = MagicMock()
    engine.manage.return_value = {"ok": True}
    coordinator = SimpleNamespace(engine=engine, async_request_refresh=AsyncMock())
    hass.data["overhead"] = {"entries": {"one": coordinator}}
    c = SimpleNamespace(
        user=SimpleNamespace(is_admin=False),
        send_error=MagicMock(),
        send_result=MagicMock(),
    )
    msg = {"id": 1, "type": "overhead/manage", "entry_id": "one", "action": "purge"}
    await handle(hass, c, msg)
    assert c.send_error.call_args.args[1] == "unauthorized"
    engine.manage.assert_not_called()
    await handle(hass, c, {**msg, "action": "status"})
    engine.manage.assert_called_once_with("status", "", 0)
    engine.reset_mock()
    await handle(hass, c, {**msg, "entry_id": "missing"})
    assert c.send_error.call_args.args[1] == "not_found"
    engine.manage.assert_not_called()
    await hass.async_stop()


@pytest.mark.asyncio
async def test_real_home_assistant_setup_sensor_and_unload(tmp_path, monkeypatch):
    """Exercise HA's actual loader, config-entry lifecycle and sensor platform."""
    import shutil
    from homeassistant import config_entries, loader
    from homeassistant.setup import async_setup_component

    root = Path(__file__).resolve().parents[1]
    shutil.copytree(
        root / "custom_components",
        tmp_path / "custom_components",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    hass = HomeAssistant(str(tmp_path))
    hass.config.latitude, hass.config.longitude = 52, 13
    hass.config.time_zone = "Europe/Berlin"
    # HA's loader imports custom_components from its config directory.
    import sys

    sys.path.insert(0, str(tmp_path))
    loader.async_setup(hass)
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    from homeassistant.bootstrap import async_load_base_functionality

    assert await async_load_base_functionality(hass)
    from homeassistant.auth import auth_manager_from_config

    hass.auth = await auth_manager_from_config(hass, [{"type": "homeassistant"}], [])
    # Block external calls while exercising the complete installed integration.
    integration = await loader.async_get_integration(hass, "overhead")
    component = await integration.async_get_component()
    monkeypatch.setattr(
        component.Engine,
        "poll",
        lambda self: {
            "count": 0,
            "nearest": {},
            "error": None,
            "feed": "offline test",
            "updated": 1,
        },
    )
    try:
        assert await async_setup_component(
            hass,
            "overhead",
            {"http": {"server_host": "127.0.0.1", "server_port": 18129}},
        )
        entry = config_entries.ConfigEntry(
            domain="overhead",
            title="Test observer",
            data={"latitude": 52, "longitude": 13},
            options={},
            source="user",
            version=1,
            minor_version=1,
            unique_id=None,
            discovery_keys={},
            subentries_data=[],
        )
        hass.config_entries._entries[entry.entry_id] = entry
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.entry_id in hass.data["overhead"]["entries"]
        assert len(hass.states.async_all("sensor")) == 2
        assert any(s.state == "0" for s in hass.states.async_all("sensor"))
        engine = entry.runtime_data.engine
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert entry.entry_id not in hass.data["overhead"]["entries"]
        assert engine.closed
    finally:
        await hass.async_stop()
        sys.path.remove(str(tmp_path))
