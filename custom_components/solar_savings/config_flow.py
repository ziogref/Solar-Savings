"""Config flow for Solar Savings integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_PEAK_SCHEDULE,
    CONF_ON_PEAK_RATE,
    CONF_OFF_PEAK_RATE,
    CONF_EXPORT_RATE,
    CONF_SOLAR_GENERATION_ENTITY,
    CONF_GRID_IMPORT_ENTITY,
    CONF_GRID_EXPORT_ENTITY,
)

class SolarSavingsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Savings."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return SolarSavingsOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(
                title="Solar Savings", 
                data=user_input
            )

        # Define the form schema
        data_schema = vol.Schema(
            {
                # Inputs
                vol.Required(CONF_SOLAR_GENERATION_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                ),
                vol.Required(CONF_GRID_IMPORT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                ),
                vol.Required(CONF_GRID_EXPORT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                ),
                # Schedule & Rates
                vol.Required(CONF_PEAK_SCHEDULE): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="schedule")
                ),
                vol.Optional(CONF_ON_PEAK_RATE, default=0.0): vol.Coerce(float),
                vol.Optional(CONF_OFF_PEAK_RATE, default=0.0): vol.Coerce(float),
                vol.Optional(CONF_EXPORT_RATE, default=0.0): vol.Coerce(float),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

class SolarSavingsOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Solar Savings."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Helper to get current value from options or data
        def get_current(key, default=None):
            return self.config_entry.options.get(
                key, self.config_entry.data.get(key, default)
            )

        schema = vol.Schema(
            {
                vol.Optional(CONF_SOLAR_GENERATION_ENTITY, description={"suggested_value": get_current(CONF_SOLAR_GENERATION_ENTITY)}): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                ),
                vol.Optional(CONF_GRID_IMPORT_ENTITY, description={"suggested_value": get_current(CONF_GRID_IMPORT_ENTITY)}): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                ),
                vol.Optional(CONF_GRID_EXPORT_ENTITY, description={"suggested_value": get_current(CONF_GRID_EXPORT_ENTITY)}): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                ),
                vol.Optional(CONF_PEAK_SCHEDULE, description={"suggested_value": get_current(CONF_PEAK_SCHEDULE)}): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="schedule")
                ),
                vol.Optional(CONF_ON_PEAK_RATE, default=get_current(CONF_ON_PEAK_RATE, 0.0)): vol.Coerce(float),
                vol.Optional(CONF_OFF_PEAK_RATE, default=get_current(CONF_OFF_PEAK_RATE, 0.0)): vol.Coerce(float),
                vol.Optional(CONF_EXPORT_RATE, default=get_current(CONF_EXPORT_RATE, 0.0)): vol.Coerce(float),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)