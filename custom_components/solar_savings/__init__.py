"""The Solar Savings integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import DOMAIN

# Add SELECT to the supported platforms
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.DATE, Platform.SELECT]

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solar Savings from a config entry."""
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    async def check_rates_now(_):
        await apply_scheduled_rates(hass, entry)

    # Schedule the daily check and register CLEANUP
    entry.async_on_unload(
        async_track_time_change(hass, check_rates_now, hour=0, minute=0, second=1)
    )

    # Check immediately on startup/reload
    await check_rates_now(None)

    return True

async def apply_scheduled_rates(hass: HomeAssistant, entry: ConfigEntry):
    """Check if today is the day to apply new rates."""
    
    scheduled_date_str = entry.options.get("scheduled_date")
    
    if not scheduled_date_str:
        return 

    # Use HA's timezone aware 'now', then get the date
    today_str = dt_util.now().date().isoformat()

    if today_str >= scheduled_date_str:
        _LOGGER.info("Solar Savings: Applying scheduled changes.")
        
        # Get future values
        future_on = entry.options.get("future_on_peak_rate")
        future_off = entry.options.get("future_off_peak_rate")
        future_export = entry.options.get("future_export_rate")
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

        if future_export is not None and future_export > 0:
            new_options["export_rate"] = future_export
            new_options["future_export_rate"] = 0.0
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


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)