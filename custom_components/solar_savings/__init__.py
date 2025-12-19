"""The Solar Savings integration."""
from __future__ import annotations

import logging
from datetime import date
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change

from .const import DOMAIN

# Add DATE to the supported platforms
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.DATE]

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solar Savings from a config entry."""
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(update_listener))

    # Set up a daily check at midnight (00:00:01) to see if we need to apply new rates
    async_track_time_change(hass, check_scheduled_rates(hass, entry), hour=0, minute=0, second=1)

    return True

def check_scheduled_rates(hass: HomeAssistant, entry: ConfigEntry):
    """Return a wrapper to be called by the scheduler."""
    async def _check_wrapper(now):
        """Check if today is the day to apply new rates."""
        
        # Get the scheduled date string (YYYY-MM-DD)
        scheduled_date_str = entry.options.get("scheduled_date")
        
        if not scheduled_date_str:
            return # No schedule set

        today_str = date.today().isoformat()

        # If today matches (or is after) the scheduled date
        if today_str >= scheduled_date_str:
            _LOGGER.info("Solar Savings: Applying scheduled rate changes.")
            
            # Get future values
            future_on = entry.options.get("future_on_peak_rate")
            future_off = entry.options.get("future_off_peak_rate")

            # Prepare new options
            new_options = entry.options.copy()

            # Apply changes ONLY if values were actually set
            if future_on is not None:
                new_options["on_peak_rate"] = future_on
                new_options["future_on_peak_rate"] = 0.0 # Reset future
            
            if future_off is not None:
                new_options["off_peak_rate"] = future_off
                new_options["future_off_peak_rate"] = 0.0 # Reset future

            # Clear the date so it doesn't run again
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