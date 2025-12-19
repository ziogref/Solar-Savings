"""Sensor platform for Solar Savings."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
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
    """Set up the Solar Savings sensors."""
    
    # Currently we have moved the rate inputs to number.py
    # This file is reserved for future calculated sensors (like Total Savings)
    entities = []

    # logic for future sensors will go here...
    
    async_add_entities(entities)


class SolarSavingsSensor(SensorEntity):
    """Representation of a Solar Savings Sensor."""

    _attr_has_entity_name = True

    def __init__(
        self, 
        name: str, 
        value: float, 
        entry_id: str, 
        unique_suffix: str
    ) -> None:
        """Initialize the sensor."""
        self._attr_name = name
        self._attr_native_value = value
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        
        self._attr_native_unit_of_measurement = "AUD"
        self._attr_icon = "mdi:cash"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Solar Savings",
            manufacturer="Solar Savings Integration",
            model="Savings Calculator",
        )