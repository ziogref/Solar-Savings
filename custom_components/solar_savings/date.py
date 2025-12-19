"""Date platform for Solar Savings."""
from __future__ import annotations

from datetime import date
from homeassistant.components.date import DateEntity
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
    """Set up the Solar Savings date entity."""
    
    async_add_entities([
        SolarSavingsEffectiveDate(hass, entry)
    ])


class SolarSavingsEffectiveDate(DateEntity):
    """Representation of the Effective Date for rate changes."""

    _attr_has_entity_name = True
    _attr_name = "Effective Date"
    _attr_icon = "mdi:calendar-clock"
    _attr_entity_category = EntityCategory.CONFIG # Appears in Configuration section

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the date entity."""
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_scheduled_date"

    @property
    def native_value(self) -> date | None:
        """Return the value of the date."""
        date_str = self._entry.options.get("scheduled_date")
        if date_str:
            return date.fromisoformat(date_str)
        return None

    async def async_set_value(self, value: date) -> None:
        """Update the date."""
        new_options = self._entry.options.copy()
        new_options["scheduled_date"] = value.isoformat()
        
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