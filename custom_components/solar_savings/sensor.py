"""Sensor platform for Solar Savings."""
from __future__ import annotations

from homeassistant.components.sensor import (
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
    
    # Retrieve options (updated via configure menu or scheduler), fallback to data, fallback to 0.0
    on_peak = entry.options.get("on_peak_rate", entry.data.get("on_peak_rate", 0.0))
    off_peak = entry.options.get("off_peak_rate", entry.data.get("off_peak_rate", 0.0))

    entities = []

    # 1. On Peak Rate Sensor
    entities.append(
        SolarSavingsSensor(
            name="On Peak Rate",
            value=on_peak,
            entry_id=entry.entry_id,
            unique_suffix="on_peak_rate"
        )
    )

    # 2. Off Peak Rate Sensor
    entities.append(
        SolarSavingsSensor(
            name="Off Peak Rate",
            value=off_peak,
            entry_id=entry.entry_id,
            unique_suffix="off_peak_rate"
        )
    )
    
    async_add_entities(entities)


class SolarSavingsSensor(SensorEntity):
    """Representation of a Solar Savings Sensor."""

    _attr_has_entity_name = True
    # We use MEASUREMENT so it graphs as a continuous line
    # We do NOT use device_class="monetary" because HA enforces "TOTAL" state class for monetary
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "c/kWh"
    _attr_icon = "mdi:currency-usd"

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

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Solar Savings",
            manufacturer="Solar Savings Integration",
            model="Savings Calculator",
        )