"""Config flow for Solar Savings integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DOMAIN

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

        # Define the form schema: Rate fields + Schedule Selector
        data_schema = vol.Schema(
            {
                vol.Required("peak_schedule"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="schedule")
                ),
                vol.Optional("on_peak_rate", default=0.0): vol.Coerce(float),
                vol.Optional("off_peak_rate", default=0.0): vol.Coerce(float),
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

        # Get current values
        current_on_peak = self.config_entry.options.get(
            "on_peak_rate", self.config_entry.data.get("on_peak_rate", 0.0)
        )
        current_off_peak = self.config_entry.options.get(
            "off_peak_rate", self.config_entry.data.get("off_peak_rate", 0.0)
        )
        current_schedule = self.config_entry.options.get(
            "peak_schedule", self.config_entry.data.get("peak_schedule")
        )

        schema = vol.Schema(
            {
                vol.Optional("peak_schedule", description={"suggested_value": current_schedule}): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="schedule")
                ),
                vol.Optional("on_peak_rate", default=current_on_peak): vol.Coerce(float),
                vol.Optional("off_peak_rate", default=current_off_peak): vol.Coerce(float),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)