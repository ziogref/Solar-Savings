"""The Solar Savings integration."""
from __future__ import annotations

import logging
from datetime import date
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change

from .const import DOMAIN

# Add SELECT to the supported platforms
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.DATE, Platform.SELECT]

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solar Savings from a config entry."""
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    # Daily check at midnight
    async_track_time_change(hass, check_scheduled_rates(hass, entry), hour=0, minute=0, second=1)

    return True

def check_scheduled_rates(hass: HomeAssistant, entry: ConfigEntry):
    """Return a wrapper to be called by the scheduler."""
    async def _check_wrapper(now):
        """Check if today is the day to apply new rates."""
        
        scheduled_date_str = entry.options.get("scheduled_date")
        
        if not scheduled_date_str:
            return 

        today_str = date.today().isoformat()

        if today_str >= scheduled_date_str:
            _LOGGER.info("Solar Savings: Applying scheduled changes.")
            
            # Get future values
            future_on = entry.options.get("future_on_peak_rate")
            future_off = entry.options.get("future_off_peak_rate")
            future_schedule = entry.options.get("future_peak_schedule")

            new_options = entry.options.copy()
            changes_made = False

            # Apply Rates
            if future_on is not None and future_on > 0:
                new_options["on_peak_rate"] = future_on
                new_options["future_on_peak_rate"] = 0.0
                changes_made = True
            
            if future_off is not None and future_off > 0:
                new_options["off_peak_rate"] = future_off
                new_options["future_off_peak_rate"] = 0.0
                changes_made = True

            # Apply Schedule
            if future_schedule:
                new_options["peak_schedule"] = future_schedule
                new_options["future_peak_schedule"] = None # Reset future
                changes_made = True

            if changes_made:
                # Clear the date
                new_options["scheduled_date"] = None
                
                # Save and reload
                hass.config_entries.async_update_entry(entry, options=new_options)
    
    return _check_wrapper


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)