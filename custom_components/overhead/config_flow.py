"""UI configuration for one observation location per entry."""

import probatio as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from .const import DOMAIN
from .validation import DEFAULTS, settings_of


def schema(values, artwork=False):
    fields = {
        vol.Required("name", default=values["name"]): str,
        vol.Required("latitude", default=values["latitude"]): vol.Coerce(float),
        vol.Required("longitude", default=values["longitude"]): vol.Coerce(float),
        vol.Required("radius_km", default=values["radius_km"]): vol.In(
            ["5", "10", "15", "25", "35", "50", "80"]
        ),
        vol.Required("source", default=values["source"]): vol.In(
            ["adsb_lol", "receiver"]
        ),
        vol.Optional("receiver_url", default=values["receiver_url"]): str,
        vol.Optional("contact", default=values["contact"]): str,
    }
    if artwork:
        fields.update(
            {
                vol.Optional(
                    "fal_api_key", default=values["fal_api_key"]
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                vol.Required(
                    "generation_enabled", default=values["generation_enabled"]
                ): bool,
                vol.Required("gen_daily_usd", default=values["gen_daily_usd"]): vol.All(
                    vol.Coerce(float), vol.Range(min=0, max=100)
                ),
                vol.Required("gen_parallel", default=values["gen_parallel"]): vol.In(
                    [1, 2, 3]
                ),
                vol.Required("logo_source", default=values["logo_source"]): vol.In(
                    ["daisycon", "kiwi"]
                ),
                vol.Optional(
                    "visitor_refs", default=values["visitor_refs"]
                ): TextSelector(TextSelectorConfig(multiline=True)),
                vol.Required("cache_mb", default=values["cache_mb"]): vol.All(
                    vol.Coerce(int), vol.Range(min=64, max=4096)
                ),
            }
        )
    return vol.Schema(fields)


class OverheadConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        defaults = {
            **DEFAULTS,
            "latitude": self.hass.config.latitude,
            "longitude": self.hass.config.longitude,
            "timezone": self.hass.config.time_zone,
        }
        errors = {}
        if user_input is not None:
            try:
                values = settings_of({**defaults, **user_input})
            except (ValueError, TypeError, KeyError):
                errors["base"] = "invalid_settings"
            else:
                return self.async_create_entry(title=values["name"], data=values)
        return self.async_show_form(
            step_id="user",
            data_schema=schema({**defaults, **(user_input or {})}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OverheadOptionsFlow()


class OverheadOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input=None):
        values = {**DEFAULTS, **self.config_entry.data, **self.config_entry.options}
        errors = {}
        if user_input is not None:
            try:
                values = settings_of(
                    {**values, **user_input, "timezone": self.hass.config.time_zone}
                )
            except (ValueError, TypeError, KeyError):
                errors["base"] = "invalid_settings"
            else:
                return self.async_create_entry(title="", data=values)
        return self.async_show_form(
            step_id="init", data_schema=schema(values, artwork=True), errors=errors
        )
