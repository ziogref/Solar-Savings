"""Sensor platform for Solar Savings."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Solar Savings sensor."""
    
    # Retrieve data from the config entry
    name = entry.data["test_name"]
    value = entry.data["test_value"]

    # Create the sensor instance
    sensor = SolarSavingsSensor(name, value, entry.entry_id)
    
    async_add_entities([sensor])


class SolarSavingsSensor(SensorEntity):
    """Representation of a Solar Savings Sensor."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:cash"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "AUD"

    def __init__(self, name: str, value: float, entry_id: str) -> None:
        """Initialize the sensor."""
        self._attr_name = name
        self._attr_native_value = value
        # Setting unique_id ensures you can edit settings in the UI later
        self._attr_unique_id = f"{entry_id}_test_entity"