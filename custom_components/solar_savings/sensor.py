"""Sensor platform for Solar Savings."""
from __future__ import annotations

import logging
from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
    RestoreSensor,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfEnergy

from .const import (
    DOMAIN, 
    CONF_PEAK_SCHEDULE,
    CONF_ON_PEAK_RATE,
    CONF_OFF_PEAK_RATE,
    CONF_EXPORT_RATE,
    CONF_SOLAR_GENERATION_ENTITY,
    CONF_GRID_IMPORT_ENTITY,
    CONF_GRID_EXPORT_ENTITY
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Solar Savings sensors."""
    
    # Configuration
    on_peak = entry.options.get(CONF_ON_PEAK_RATE, entry.data.get(CONF_ON_PEAK_RATE, 0.0))
    off_peak = entry.options.get(CONF_OFF_PEAK_RATE, entry.data.get(CONF_OFF_PEAK_RATE, 0.0))
    export_rate = entry.options.get(CONF_EXPORT_RATE, entry.data.get(CONF_EXPORT_RATE, 0.0))
    active_schedule = entry.options.get(CONF_PEAK_SCHEDULE, entry.data.get(CONF_PEAK_SCHEDULE, "None"))
    
    # Input Entities
    gen_entity = entry.options.get(CONF_SOLAR_GENERATION_ENTITY, entry.data.get(CONF_SOLAR_GENERATION_ENTITY))
    imp_entity = entry.options.get(CONF_GRID_IMPORT_ENTITY, entry.data.get(CONF_GRID_IMPORT_ENTITY))
    exp_entity = entry.options.get(CONF_GRID_EXPORT_ENTITY, entry.data.get(CONF_GRID_EXPORT_ENTITY))

    entities = []

    # --- Existing Helper Sensors ---
    entities.append(SolarSavingsTextSensor("Active Schedule", active_schedule, entry.entry_id, "mdi:calendar-check"))
    entities.append(SolarSavingsRateSensor("On Peak Rate", on_peak, entry.entry_id, "on_peak_rate"))
    entities.append(SolarSavingsRateSensor("Off Peak Rate", off_peak, entry.entry_id, "off_peak_rate"))
    entities.append(SolarSavingsExportSensor(hass, "Export Rate (Cents)", export_rate, entry.entry_id, "export_rate_cents", "cents"))
    entities.append(SolarSavingsExportSensor(hass, "Export Rate (Dollars)", export_rate, entry.entry_id, "export_rate_dollars", "dollars"))

    if active_schedule and active_schedule != "None":
        entities.append(SolarSavingsCurrentRateSensor(hass, entry.entry_id, active_schedule, on_peak, off_peak, "Current Import Rate (Cents)", "current_import_rate_cents", "cents"))
        entities.append(SolarSavingsCurrentRateSensor(hass, entry.entry_id, active_schedule, on_peak, off_peak, "Current Import Rate (Dollars)", "current_import_rate_dollars", "dollars"))

    # --- New Tracking Sensors (Accumulators) ---
    if gen_entity and imp_entity and exp_entity:
        
        # 1. Total Generated Energy (Tracked)
        entities.append(SolarSavingsEnergyAccumulator(
            hass, entry.entry_id, "Total Generated Energy", "total_generated_energy", 
            gen_entity, "mdi:solar-power"
        ))

        # 2. Total Imported Energy (Tracked)
        entities.append(SolarSavingsEnergyAccumulator(
            hass, entry.entry_id, "Total Imported Energy", "total_imported_energy", 
            imp_entity, "mdi:transmission-tower-import"
        ))

        # 3. Total Exported Energy (Tracked)
        entities.append(SolarSavingsEnergyAccumulator(
            hass, entry.entry_id, "Total Exported Energy", "total_exported_energy", 
            exp_entity, "mdi:transmission-tower-export"
        ))

        # 4. Total Self Consumed Energy (Calculated from tracked values)
        # This sensor listens to the Integration's OWN Total Gen and Total Exp sensors
        entities.append(SolarSavingsSelfConsumptionSensor(
            hass, entry.entry_id, 
            f"sensor.solar_savings_total_generated_energy", # Assuming default naming
            f"sensor.solar_savings_total_exported_energy"
        ))

        # 5. Total Import Cost ($)
        entities.append(SolarSavingsFinancialAccumulator(
            hass, entry.entry_id, "Total Import Cost", "total_import_cost",
            imp_entity, active_schedule, on_peak, off_peak, 0.0, "import"
        ))

        # 6. Total Export Credit ($)
        entities.append(SolarSavingsFinancialAccumulator(
            hass, entry.entry_id, "Total Export Credit", "total_export_credit",
            exp_entity, active_schedule, on_peak, off_peak, export_rate, "export"
        ))

        # 7. Total Solar Savings ($) (Complex logic: Self Consumption Savings + Export Income)
        # We need to listen to BOTH Generation and Export inputs to calculate this correctly in real time
        entities.append(SolarSavingsSavingsAccumulator(
            hass, entry.entry_id, "Total Solar Savings", "total_solar_savings",
            gen_entity, exp_entity, active_schedule, on_peak, off_peak, export_rate
        ))

    async_add_entities(entities)


# --- Helper Function for Rate Logic ---
def get_current_import_rate_cents(hass, schedule_entity_id, on_peak_rate, off_peak_rate):
    """Determine the current import rate in cents based on schedule."""
    if not schedule_entity_id or schedule_entity_id == "None":
        return off_peak_rate # Default to off peak if no schedule
    
    state = hass.states.get(schedule_entity_id)
    if state and state.state == STATE_ON:
        return on_peak_rate
    return off_peak_rate


# --- Base Class for Accumulators ---
class SolarSavingsAccumulator(RestoreSensor):
    """Base class for sensors that accumulate values over time, ignoring previous history."""
    
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL
    
    def __init__(self, hass, entry_id, name, unique_suffix, source_entity_id, icon):
        self.hass = hass
        self._entry_id = entry_id
        self._source_entity_id = source_entity_id
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        self._attr_icon = icon
        self._attr_native_value = 0.0
        self._last_source_value = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Solar Savings",
            manufacturer="Solar Savings Integration",
            model="Savings Calculator",
        )

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # 1. Restore previous accumulated value
        state = await self.async_get_last_state()
        if state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                self._attr_native_value = float(state.state)
            except ValueError:
                self._attr_native_value = 0.0

        # 2. Get current source value to start tracking deltas from NOW
        # We do NOT add the initial value. We only add changes from this point on.
        current_source = self.hass.states.get(self._source_entity_id)
        if current_source and current_source.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                self._last_source_value = float(current_source.state)
            except ValueError:
                self._last_source_value = None

        # 3. Listen for changes
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._source_entity_id], self._handle_state_change
            )
        )

    def _handle_state_change(self, event):
        """Handle updates from the source entity."""
        new_state = event.data.get("new_state")
        
        if new_state is None or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return

        try:
            current_value = float(new_state.state)
        except ValueError:
            return

        # Initialize last_value if it was missing (first run)
        if self._last_source_value is None:
            self._last_source_value = current_value
            return

        # Calculate Delta
        delta = current_value - self._last_source_value
        
        # Ignore resets (negative delta) or tiny noise
        if delta < 0:
            self._last_source_value = current_value
            return
            
        self._last_source_value = current_value
        self._process_delta(delta)
        self.async_write_ha_state()

    def _process_delta(self, delta):
        """Override this in subclasses to do specific math."""
        self._attr_native_value += delta


# --- Specific Implementations ---

class SolarSavingsEnergyAccumulator(SolarSavingsAccumulator):
    """Tracks simple energy accumulation (kWh)."""
    
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def _process_delta(self, delta):
        self._attr_native_value += delta


class SolarSavingsFinancialAccumulator(SolarSavingsAccumulator):
    """Tracks financial costs/credits based on rates."""
    
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_suggested_display_precision = 2

    def __init__(self, hass, entry_id, name, unique_suffix, source_entity_id, 
                 schedule_id, on_peak, off_peak, export_rate, mode):
        # Modes: "import" (costs money), "export" (makes money)
        super().__init__(hass, entry_id, name, unique_suffix, source_entity_id, "mdi:currency-usd")
        self._schedule_id = schedule_id
        self._on_peak = on_peak
        self._off_peak = off_peak
        self._export_rate = export_rate
        self._mode = mode
        self._attr_native_unit_of_measurement = hass.config.currency

    def _process_delta(self, delta):
        # 1. Get Rate (Cents)
        if self._mode == "export":
            rate_cents = self._export_rate
        else:
            rate_cents = get_current_import_rate_cents(
                self.hass, self._schedule_id, self._on_peak, self._off_peak
            )
        
        # 2. Convert to Dollars/Currency and accumulate
        cost_delta = delta * (rate_cents / 100.0)
        self._attr_native_value += cost_delta


class SolarSavingsSavingsAccumulator(RestoreSensor):
    """
    Complex logic: Tracks Total Savings.
    Savings = (Self Consumed * Import Rate) + (Exported * Export Rate)
    
    Logic derived as:
    When Generation increases: We assume it's saved. Add (Delta * ImportRate).
    When Export increases: We realize it wasn't self-consumed. 
                           Subtract (Delta * ImportRate) AND Add (Delta * ExportRate).
                           Effectively: Add Delta * (ExportRate - ImportRate).
    """
    
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:piggy-bank"

    def __init__(self, hass, entry_id, name, unique_suffix, 
                 gen_entity, exp_entity, schedule_id, on_peak, off_peak, export_rate):
        self.hass = hass
        self._entry_id = entry_id
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        
        self._gen_entity = gen_entity
        self._exp_entity = exp_entity
        self._schedule_id = schedule_id
        self._on_peak = on_peak
        self._off_peak = off_peak
        self._export_rate = export_rate
        
        self._attr_native_value = 0.0
        self._attr_native_unit_of_measurement = hass.config.currency

        self._last_gen_val = None
        self._last_exp_val = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Solar Savings",
            manufacturer="Solar Savings Integration",
            model="Savings Calculator",
        )

    async def async_added_to_hass(self) -> None:
        """Handle addition."""
        await super().async_added_to_hass()
        
        # Restore
        state = await self.async_get_last_state()
        if state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                self._attr_native_value = float(state.state)
            except ValueError:
                self._attr_native_value = 0.0

        # Initialize trackers
        self._init_tracker(self._gen_entity, "_last_gen_val")
        self._init_tracker(self._exp_entity, "_last_exp_val")

        # Listen
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._gen_entity, self._exp_entity], self._handle_change
            )
        )

    def _init_tracker(self, entity_id, attr_name):
        state = self.hass.states.get(entity_id)
        if state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                setattr(self, attr_name, float(state.state))
            except ValueError:
                setattr(self, attr_name, None)

    def _handle_change(self, event):
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        
        if not new_state or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
            
        try:
            val = float(new_state.state)
        except ValueError:
            return

        import_rate_cents = get_current_import_rate_cents(
            self.hass, self._schedule_id, self._on_peak, self._off_peak
        )
        import_rate_dollars = import_rate_cents / 100.0
        export_rate_dollars = self._export_rate / 100.0

        delta = 0.0

        if entity_id == self._gen_entity:
            if self._last_gen_val is not None:
                delta = val - self._last_gen_val
                if delta > 0:
                    # Gen Delta contributes to savings assuming self-consumption initially
                    self._attr_native_value += delta * import_rate_dollars
            self._last_gen_val = val

        elif entity_id == self._exp_entity:
            if self._last_exp_val is not None:
                delta = val - self._last_exp_val
                if delta > 0:
                    # Export Delta means it wasn't self consumed.
                    # Remove the Import Rate we added, and add Export Rate instead.
                    # Math: val += delta * (ExportRate - ImportRate)
                    correction = delta * (export_rate_dollars - import_rate_dollars)
                    self._attr_native_value += correction
            self._last_exp_val = val
        
        self.async_write_ha_state()


class SolarSavingsSelfConsumptionSensor(SensorEntity):
    """Tracks Self Consumption Energy = Total Gen - Total Export."""
    
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:home-lightning-bolt"

    def __init__(self, hass, entry_id, gen_sensor_id, exp_sensor_id):
        self.hass = hass
        self._entry_id = entry_id
        self._attr_name = "Total Self Consumed Energy"
        self._attr_unique_id = f"{entry_id}_total_self_consumed"
        self._gen_sensor = gen_sensor_id
        self._exp_sensor = exp_sensor_id

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        # Find the actual entity IDs if they are predictable
        # Since we generate unique IDs for the accumulators, we need to find their entity_ids.
        # However, passed in args are likely strings like "sensor.solar_savings_total_generated_energy"
        # Ideally, we should listen to state changes of the other sensors we created.
        
        # Because we create them in the same list, we don't know their final entity_ids yet if HA renames them.
        # A safer bet is to listen to the *source* entities and replicate logic, OR
        # rely on the predictable entity ID format if the user hasn't renamed them.
        
        # Better approach: Re-implement simple accumulation logic here? 
        # No, that's duplicative.
        # Let's listen to the source entities directly and calc Gen - Exp.
        # Wait, Gen - Exp of the *accumulated* values.
        # So we really want (AccumulatedGen - AccumulatedExp).
        
        # To make this robust, I will update this sensor to perform the same Restore/Accumulate logic
        # but for both Gen and Exp, simply to subtract them.
        pass # Logic handled below

    # RE-WRITING CLASS TO BE STANDALONE ACCUMULATOR TO AVOID DEPENDENCY ISSUES
    
    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Not using RestoreSensor here because we can recalculate from the other two if we knew them.
        # But let's just piggyback on the same logic as SavingsAccumulator but for Energy.
        
        # Initialize
        self._attr_native_value = 0.0
        
        # We need access to the current values of our own integration's sensors.
        # Since we can't easily guarantee their IDs, I will replicate the tracking of the raw source sensors.
        
        # Hack: We need persistent storage for this too then.
        # Ideally, this should inherit from SolarSavingsSavingsAccumulator logic but with rates = 1.
        pass

# I'll implement a clean version of SelfConsumption that tracks both sources using the base logic 
# but specifically for Energy.

class SolarSavingsSelfConsumptionSensor(RestoreSensor):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:home-lightning-bolt"

    def __init__(self, hass, entry_id, gen_entity_source, exp_entity_source):
        # NOTE: accepting SOURCE entities, not the resulting sensors
        self.hass = hass
        self._entry_id = entry_id
        self._attr_name = "Total Self Consumed Energy"
        self._attr_unique_id = f"{entry_id}_total_self_consumed"
        self._gen_entity = gen_entity_source
        self._exp_entity = exp_entity_source
        self._attr_native_value = 0.0
        self._last_gen = None
        self._last_exp = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Solar Savings",
            manufacturer="Solar Savings Integration",
            model="Savings Calculator",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                self._attr_native_value = float(state.state)
            except ValueError:
                self._attr_native_value = 0.0
        
        # Init trackers
        self._init_tracker(self._gen_entity, "_last_gen")
        self._init_tracker(self._exp_entity, "_last_exp")

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._gen_entity, self._exp_entity], self._handle_change
            )
        )

    def _init_tracker(self, entity, attr):
        s = self.hass.states.get(entity)
        if s and s.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                setattr(self, attr, float(s.state))
            except ValueError:
                pass

    def _handle_change(self, event):
        eid = event.data.get("entity_id")
        new_s = event.data.get("new_state")
        if not new_s or new_s.state in (STATE_UNKNOWN, STATE_UNAVAILABLE): return
        try:
            val = float(new_s.state)
        except ValueError: return

        if eid == self._gen_entity:
            if self._last_gen is not None:
                d = val - self._last_gen
                if d > 0: self._attr_native_value += d
            self._last_gen = val
        elif eid == self._exp_entity:
            if self._last_exp is not None:
                d = val - self._last_exp
                if d > 0: self._attr_native_value -= d # Export reduces self consumption
            self._last_exp = val
        
        self.async_write_ha_state()

# --- Legacy Sensors (kept for compatibility) ---
class SolarSavingsTextSensor(SensorEntity):
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

class SolarSavingsExportSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:home-export-outline"
    def __init__(self, hass: HomeAssistant, name: str, value: float, entry_id: str, unique_suffix: str, mode: str) -> None:
        self._attr_name = name
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        if mode == "dollars":
            currency = hass.config.currency
            self._attr_native_unit_of_measurement = f"{currency}/kWh"
            self._attr_native_value = value / 100.0
            self._attr_suggested_display_precision = 4
        else:
            self._attr_native_unit_of_measurement = "c/kWh"
            self._attr_native_value = value
            self._attr_suggested_display_precision = 2
    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Solar Savings",
            manufacturer="Solar Savings Integration",
            model="Savings Calculator",
        )

class SolarSavingsCurrentRateSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:cash-fast"
    def __init__(self, hass, entry_id, schedule_entity_id, on_peak, off_peak, name, unique_suffix, mode) -> None:
        self.hass = hass
        self._entry_id = entry_id
        self._schedule_entity_id = schedule_entity_id
        self._on_peak = on_peak
        self._off_peak = off_peak
        self._mode = mode
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        if self._mode == "dollars":
            currency = hass.config.currency
            self._attr_native_unit_of_measurement = f"{currency}/kWh"
            self._attr_suggested_display_precision = 4 
        else:
            self._attr_native_unit_of_measurement = "c/kWh"
            self._attr_suggested_display_precision = 2 

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._schedule_entity_id], self._handle_schedule_change
            )
        )
        self._update_state()

    @callback
    def _handle_schedule_change(self, event) -> None:
        self._update_state()
        self.async_write_ha_state()

    def _update_state(self) -> None:
        state = self.hass.states.get(self._schedule_entity_id)
        if state and state.state == STATE_ON:
            current_rate_cents = self._on_peak
            status = "On Peak"
        else:
            current_rate_cents = self._off_peak
            status = "Off Peak"
        if self._mode == "dollars":
            self._attr_native_value = current_rate_cents / 100.0
        else:
            self._attr_native_value = current_rate_cents
        self._attr_extra_state_attributes = {"status": status, "raw_cents": current_rate_cents}
    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Solar Savings",
            manufacturer="Solar Savings Integration",
            model="Savings Calculator",
        )