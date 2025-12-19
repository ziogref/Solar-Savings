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
    
    # Get current values
    on_peak = entry.options.get("on_peak_rate", entry.data.get("on_peak_rate", 0.0))
    off_peak = entry.options.get("off_peak_rate", entry.data.get("off_peak_rate", 0.0))
    active_schedule = entry.options.get("peak_schedule", entry.data.get("peak_schedule", "None"))

    entities = []

    # 1. Active Schedule Name (Text Sensor for confidence check)
    entities.append(
        SolarSavingsTextSensor(
            name="Active Schedule",
            value=active_schedule,
            entry_id=entry.entry_id,
            icon="mdi:calendar-check"
        )
    )

    # 2. On Peak Rate Sensor
    entities.append(
        SolarSavingsRateSensor(
            name="On Peak Rate",
            value=on_peak,
            entry_id=entry.entry_id,
            unique_suffix="on_peak_rate"
        )
    )

    # 3. Off Peak Rate Sensor
    entities.append(
        SolarSavingsRateSensor(
            name="Off Peak Rate",
            value=off_peak,
            entry_id=entry.entry_id,
            unique_suffix="off_peak_rate"
        )
    )
    
    async_add_entities(entities)


class SolarSavingsTextSensor(SensorEntity):
    """Representation of a text sensor (e.g. Active Schedule Name)."""
    
    _attr_has_entity_name = True

    def __init__(self, name: str, value: str, entry_id: str, icon: str) -> None:
        self._attr_name = name
        self._attr_native_value = value
        self._entry_id = entry_id
        self._attr_icon = icon
        self._attr_unique_id = f"{entry_id}_{name.lower().replace(' ', '_')}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Solar Savings",
            manufacturer="Solar Savings Integration",
            model="Savings Calculator",
        )


class SolarSavingsRateSensor(SensorEntity):
    """Representation of a Numeric Rate Sensor."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "c/kWh"
    _attr_icon = "mdi:currency-usd"

    def __init__(self, name: str, value: float, entry_id: str, unique_suffix: str) -> None:
        self._attr_name = name
        self._attr_native_value = value
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Solar Savings",
            manufacturer="Solar Savings Integration",
            model="Savings Calculator",
        )