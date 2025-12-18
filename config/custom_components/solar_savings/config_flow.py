"""Config flow for Solar Savings integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN

class SolarSavingsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Savings."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # When the user submits the form, create the entry
            return self.async_create_entry(
                title=user_input["test_name"], 
                data=user_input
            )

        # Define the form schema: Name (string) and Value (float)
        data_schema = vol.Schema(
            {
                vol.Required("test_name", default="Test Entity"): str,
                vol.Required("test_value", default=69420.0): float,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )