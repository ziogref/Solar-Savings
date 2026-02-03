"""Sensor platform for Solar Savings."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.const import STATE_ON

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

    # 4. Current Rate Sensor (New!)
    # Only create if a schedule is configured
    if active_schedule and active_schedule != "None":
        entities.append(
            SolarSavingsCurrentRateSensor(
                hass=hass,
                entry_id=entry.entry_id,
                schedule_entity_id=active_schedule,
                on_peak=on_peak,
                off_peak=off_peak
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


class SolarSavingsCurrentRateSensor(SensorEntity):
    """Sensor that displays the current rate based on the schedule state."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "c/kWh"
    _attr_icon = "mdi:cash-fast"

    def __init__(
        self, 
        hass: HomeAssistant, 
        entry_id: str, 
        schedule_entity_id: str, 
        on_peak: float, 
        off_peak: float
    ) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._entry_id = entry_id
        self._schedule_entity_id = schedule_entity_id
        self._on_peak = on_peak
        self._off_peak = off_peak
        
        self._attr_name = "Current Rate"
        self._attr_unique_id = f"{entry_id}_current_rate"

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        # Subscribe to state changes of the schedule entity
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._schedule_entity_id], self._handle_schedule_change
            )
        )
        # Update state immediately on add
        self._update_state()

    @callback
    def _handle_schedule_change(self, event) -> None:
        """Handle the schedule changing state."""
        self._update_state()
        self.async_write_ha_state()

    def _update_state(self) -> None:
        """Determine the current rate."""
        state = self.hass.states.get(self._schedule_entity_id)

        # Helpers in 'schedule' domain are 'on' during the schedule blocks
        if state and state.state == STATE_ON:
            self._attr_native_value = self._on_peak
            self._attr_extra_state_attributes = {"status": "On Peak"}
        else:
            # Default to Off Peak if off or unavailable
            self._attr_native_value = self._off_peak
            self._attr_extra_state_attributes = {"status": "Off Peak"}

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Solar Savings",
            manufacturer="Solar Savings Integration",
            model="Savings Calculator",
        )