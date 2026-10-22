"""Poll in the HA executor and keep saved profiles warm with no open browser."""

from datetime import timedelta
import logging
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed


class OverheadCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, engine):
        self.engine = engine
        super().__init__(
            hass,
            logging.getLogger(__name__),
            name=f"Overhead {entry.title}",
            config_entry=entry,
            update_interval=timedelta(
                seconds=30 if engine.settings["source"] == "receiver" else 60
            ),
        )

    async def _async_update_data(self):
        try:
            return await self.hass.async_add_executor_job(self.engine.poll)
        except Exception as exc:
            raise UpdateFailed(f"Overhead update failed: {type(exc).__name__}") from exc
