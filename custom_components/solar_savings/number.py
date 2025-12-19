"""Number platform for Solar Savings."""
from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Solar Savings number entities."""
    
    entities = []

    # Create editable numbers for rates
    # We map the internal config key to a friendly name
    rates = {
        "on_peak_rate": "On Peak Rate",
        "off_peak_rate": "Off Peak Rate",
    }

    for key, name in rates.items():
        entities.append(
            SolarSavingsRateNumber(
                hass=hass,
                entry=entry,
                name=name,
                config_key=key
            )
        )
    
    async_add_entities(entities)


class SolarSavingsRateNumber(NumberEntity):
    """Representation of a Solar Savings Number entity."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX # Use a text box instead of a slider for precision
    _attr_native_min_value = 0.0
    _attr_native_max_value = 1000.0 # Reasonable max cents/kWh
    _attr_native_step = 0.001 # Allow partial cents
    _attr_native_unit_of_measurement = "c/kWh"
    _attr_device_class = NumberDeviceClass.MONETARY
    _attr_icon = "mdi:currency-usd"

    def __init__(
        self, 
        hass: HomeAssistant, 
        entry: ConfigEntry, 
        name: str, 
        config_key: str
    ) -> None:
        """Initialize the number."""
        self.hass = hass
        self._entry = entry
        self._config_key = config_key
        
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{config_key}"

    @property
    def native_value(self) -> float | None:
        """Return the current value from config options."""
        # Check options first, then data, then default to 0.0
        return self._entry.options.get(
            self._config_key, 
            self._entry.data.get(self._config_key, 0.0)
        )

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        # Create a mutable copy of the current options
        new_options = self._entry.options.copy()
        
        # Update the specific value
        new_options[self._config_key] = value
        
        # Save back to Home Assistant
        # This will trigger the reload listener in __init__.py
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