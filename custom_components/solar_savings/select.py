"""Select platform for Solar Savings."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Solar Savings select entities."""
    
    async_add_entities([
        SolarSavingsFutureSchedule(hass, entry)
    ])


class SolarSavingsFutureSchedule(SelectEntity):
    """Representation of the Future Schedule selector."""

    _attr_has_entity_name = True
    _attr_name = "Future Peak Schedule"
    _attr_icon = "mdi:calendar-refresh"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the select entity."""
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_future_peak_schedule"

    @property
    def options(self) -> list[str]:
        """Return a list of available schedule entities."""
        # Find all entities in the 'schedule' domain
        schedules = self.hass.states.async_entity_ids("schedule")
        
        # If the currently selected option is not in the list (e.g. deleted), add it temporarily
        current = self.current_option
        if current and current not in schedules:
            schedules.append(current)
            
        return sorted(schedules)

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option."""
        return self._entry.options.get("future_peak_schedule")

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        new_options = self._entry.options.copy()
        new_options["future_peak_schedule"] = option
        
        self.hass.config_entries.async_update_entry(
            self._entry, 
            options=new_options
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Solar Savings",
            manufacturer="Solar Savings Integration",
            model="Savings Calculator",
        )