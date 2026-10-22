"""Small automation-friendly state; images and traffic history avoid recorder."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            OverheadSensor(entry.runtime_data, entry, "count"),
            OverheadSensor(entry.runtime_data, entry, "nearest"),
        ]
    )


class OverheadSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:airplane"

    def __init__(self, coordinator, entry, kind):
        super().__init__(coordinator)
        self.kind = kind
        self._attr_name = "Aircraft nearby" if kind == "count" else "Nearest aircraft"
        self._attr_unique_id = f"{entry.entry_id}_{kind}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Overhead",
            "model": "Aircraft observer",
        }
        if kind == "count":
            self._attr_native_unit_of_measurement = "aircraft"
            self._attr_state_class = "measurement"

    @property
    def available(self):
        return super().available and not (self.coordinator.data or {}).get("error")

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return (
            data.get("count", 0)
            if self.kind == "count"
            else data.get("nearest", {}).get("cs")
        )

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        if self.kind == "nearest":
            return data.get("nearest", {})
        return {"feed": data.get("feed", ""), "observed_at": data.get("updated", 0)}
