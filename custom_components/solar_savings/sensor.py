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
    
    # Retrieve data from the config entry (initial setup)
    name = entry.data.get("test_name", "Test Entity")
    value = entry.data.get("test_value", 0.0)
    
    # Retrieve options (updated via configure menu), fallback to data, fallback to 0.0
    on_peak = entry.options.get("on_peak_rate", entry.data.get("on_peak_rate", 0.0))
    off_peak = entry.options.get("off_peak_rate", entry.data.get("off_peak_rate", 0.0))

    entities = []

    # 1. Main Test Sensor
    entities.append(
        SolarSavingsSensor(
            name=name,
            value=value,
            entry_id=entry.entry_id,
            sensor_type="total",
            unique_suffix="test_entity"
        )
    )

    # 2. On Peak Rate Sensor
    entities.append(
        SolarSavingsSensor(
            name="On Peak Rate",
            value=on_peak,
            entry_id=entry.entry_id,
            sensor_type="rate",
            unique_suffix="on_peak_rate"
        )
    )

    # 3. Off Peak Rate Sensor
    entities.append(
        SolarSavingsSensor(
            name="Off Peak Rate",
            value=off_peak,
            entry_id=entry.entry_id,
            sensor_type="rate",
            unique_suffix="off_peak_rate"
        )
    )
    
    async_add_entities(entities)


class SolarSavingsSensor(SensorEntity):
    """Representation of a Solar Savings Sensor."""

    _attr_has_entity_name = True

    def __init__(
        self, 
        name: str, 
        value: float, 
        entry_id: str, 
        sensor_type: str, 
        unique_suffix: str
    ) -> None:
        """Initialize the sensor."""
        self._attr_name = name
        self._attr_native_value = value
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        
        # Configure attributes based on the type of sensor
        if sensor_type == "rate":
            self._attr_native_unit_of_measurement = "c/kWh"
            self._attr_icon = "mdi:currency-usd"
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_state_class = SensorStateClass.MEASUREMENT
        else:
            # Default/Test entity
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