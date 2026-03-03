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
    CONF_SYSTEM_COST,
    CONF_PTO_DATE,
    # Historical
    CONF_INITIAL_GENERATION,
    CONF_INITIAL_IMPORT,
    CONF_INITIAL_EXPORT,
    CONF_INITIAL_SELF_CONSUMED,
    CONF_INITIAL_IMPORT_COST,
    CONF_INITIAL_EXPORT_CREDIT,
    CONF_INITIAL_SELF_CONSUMED_SAVINGS,
    CONF_INITIAL_SAVINGS,
)

class SolarSavingsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Savings."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self.init_data = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return SolarSavingsOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            self.init_data = user_input
            return await self.async_step_roi()

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

    async def async_step_roi(self, user_input=None):
        """Handle the second step for ROI calculation."""
        if user_input is not None:
            self.init_data.update(user_input)
            return self.async_create_entry(
                title="Solar Savings", 
                data=self.init_data
            )

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_SYSTEM_COST): vol.Coerce(float),
                vol.Optional(CONF_PTO_DATE): selector.DateSelector(),
            }
        )

        return self.async_show_form(step_id="roi", data_schema=data_schema)

class SolarSavingsOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Solar Savings."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self.user_input_init = {}
        self.user_input_roi = {}

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            # Go to ROI step
            self.user_input_init = user_input
            return await self.async_step_roi()

        # Helper to get current value safely
        def get_current(key, default=None):
            val = self.config_entry.options.get(key, self.config_entry.data.get(key, default))
            return val if val is not None else default

        curr_gen = get_current(CONF_SOLAR_GENERATION_ENTITY)
        curr_imp = get_current(CONF_GRID_IMPORT_ENTITY)
        curr_exp = get_current(CONF_GRID_EXPORT_ENTITY)
        curr_sched = get_current(CONF_PEAK_SCHEDULE)
        
        curr_peak = get_current(CONF_ON_PEAK_RATE, 0.0)
        curr_off = get_current(CONF_OFF_PEAK_RATE, 0.0)
        curr_export = get_current(CONF_EXPORT_RATE, 0.0)
        
        schema_dict = {}

        schema_dict[vol.Optional(CONF_SOLAR_GENERATION_ENTITY, description={"suggested_value": curr_gen})] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="energy")
        )
        schema_dict[vol.Optional(CONF_GRID_IMPORT_ENTITY, description={"suggested_value": curr_imp})] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="energy")
        )
        schema_dict[vol.Optional(CONF_GRID_EXPORT_ENTITY, description={"suggested_value": curr_exp})] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="energy")
        )
        schema_dict[vol.Optional(CONF_PEAK_SCHEDULE, description={"suggested_value": curr_sched})] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="schedule")
        )

        schema_dict[vol.Optional(CONF_ON_PEAK_RATE, default=curr_peak)] = vol.Coerce(float)
        schema_dict[vol.Optional(CONF_OFF_PEAK_RATE, default=curr_off)] = vol.Coerce(float)
        schema_dict[vol.Optional(CONF_EXPORT_RATE, default=curr_export)] = vol.Coerce(float)

        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema_dict))

    async def async_step_roi(self, user_input=None):
        """Step to configure ROI."""
        if user_input is not None:
            self.user_input_roi = user_input
            return await self.async_step_history()
            
        def get_current(key, default=None):
            val = self.config_entry.options.get(key, self.config_entry.data.get(key, default))
            return val if val is not None else default
            
        curr_cost = get_current(CONF_SYSTEM_COST)
        curr_pto = get_current(CONF_PTO_DATE)
        
        schema_dict = {}
        
        if curr_cost is not None:
            schema_dict[vol.Optional(CONF_SYSTEM_COST, default=curr_cost)] = vol.Coerce(float)
        else:
            schema_dict[vol.Optional(CONF_SYSTEM_COST)] = vol.Coerce(float)

        if curr_pto is not None:
            schema_dict[vol.Optional(CONF_PTO_DATE, default=curr_pto)] = selector.DateSelector()
        else:
            schema_dict[vol.Optional(CONF_PTO_DATE)] = selector.DateSelector()
            
        return self.async_show_form(step_id="roi", data_schema=vol.Schema(schema_dict))

    async def async_step_history(self, user_input=None):
        """Step to configure historical values."""
        if user_input is not None:
            # Merge with init and roi data and create entry
            final_data = {**self.user_input_init, **self.user_input_roi, **user_input}
            return self.async_create_entry(title="", data=final_data)

        def get_current(key, default=0.0):
            val = self.config_entry.options.get(key, self.config_entry.data.get(key, default))
            return val if val is not None else default

        schema = vol.Schema({
            vol.Optional(CONF_INITIAL_GENERATION, default=get_current(CONF_INITIAL_GENERATION)): vol.Coerce(float),
            vol.Optional(CONF_INITIAL_IMPORT, default=get_current(CONF_INITIAL_IMPORT)): vol.Coerce(float),
            vol.Optional(CONF_INITIAL_EXPORT, default=get_current(CONF_INITIAL_EXPORT)): vol.Coerce(float),
            vol.Optional(CONF_INITIAL_SELF_CONSUMED, default=get_current(CONF_INITIAL_SELF_CONSUMED)): vol.Coerce(float),
            
            vol.Optional(CONF_INITIAL_IMPORT_COST, default=get_current(CONF_INITIAL_IMPORT_COST)): vol.Coerce(float),
            vol.Optional(CONF_INITIAL_EXPORT_CREDIT, default=get_current(CONF_INITIAL_EXPORT_CREDIT)): vol.Coerce(float),
            vol.Optional(CONF_INITIAL_SELF_CONSUMED_SAVINGS, default=get_current(CONF_INITIAL_SELF_CONSUMED_SAVINGS)): vol.Coerce(float),
            vol.Optional(CONF_INITIAL_SAVINGS, default=get_current(CONF_INITIAL_SAVINGS)): vol.Coerce(float),
        })

        return self.async_show_form(step_id="history", data_schema=schema)