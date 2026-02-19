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
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfEnergy
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN, 
    CONF_PEAK_SCHEDULE,
    CONF_ON_PEAK_RATE,
    CONF_OFF_PEAK_RATE,
    CONF_EXPORT_RATE,
    CONF_SOLAR_GENERATION_ENTITY,
    CONF_GRID_IMPORT_ENTITY,
    CONF_GRID_EXPORT_ENTITY,
    # History
    CONF_INITIAL_GENERATION,
    CONF_INITIAL_IMPORT,
    CONF_INITIAL_EXPORT,
    CONF_INITIAL_SELF_CONSUMED,
    CONF_INITIAL_IMPORT_COST,
    CONF_INITIAL_EXPORT_CREDIT,
    CONF_INITIAL_SELF_CONSUMED_SAVINGS,
    CONF_INITIAL_SAVINGS,
)

_LOGGER = logging.getLogger(__name__)

PERIODS = {
    "total": "Total",
    "daily": "Daily",
    "monthly": "Monthly",
    "yearly": "Yearly",
}

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

    # Helper to safe get float from options
    def get_hist(key):
        return entry.options.get(key, entry.data.get(key, 0.0))

    # Historical Values (Only applied to "total" sensors)
    hist_gen = get_hist(CONF_INITIAL_GENERATION)
    hist_imp = get_hist(CONF_INITIAL_IMPORT)
    hist_exp = get_hist(CONF_INITIAL_EXPORT)
    hist_self = get_hist(CONF_INITIAL_SELF_CONSUMED)
    hist_imp_cost = get_hist(CONF_INITIAL_IMPORT_COST)
    hist_exp_credit = get_hist(CONF_INITIAL_EXPORT_CREDIT)
    hist_self_savings = get_hist(CONF_INITIAL_SELF_CONSUMED_SAVINGS)
    hist_savings = get_hist(CONF_INITIAL_SAVINGS)

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
        
        for period_key, period_name in PERIODS.items():
            
            # Determine initial value (only for Total)
            init_gen = hist_gen if period_key == "total" else 0.0
            init_imp = hist_imp if period_key == "total" else 0.0
            init_exp = hist_exp if period_key == "total" else 0.0
            init_self = hist_self if period_key == "total" else 0.0
            init_imp_cost = hist_imp_cost if period_key == "total" else 0.0
            init_exp_credit = hist_exp_credit if period_key == "total" else 0.0
            init_savings = hist_savings if period_key == "total" else 0.0
            init_self_savings = hist_self_savings if period_key == "total" else 0.0

            # --- Define the Primary Sensor ---

            # 1. Generated Energy
            s1 = SolarSavingsEnergyAccumulator(
                hass, entry.entry_id, f"{period_name} Generated Energy", f"{period_key}_generated_energy", 
                gen_entity, "mdi:solar-power", period_key, init_gen
            )
            entities.append(s1)

            # 2. Imported Energy
            s2 = SolarSavingsEnergyAccumulator(
                hass, entry.entry_id, f"{period_name} Imported Energy", f"{period_key}_imported_energy", 
                imp_entity, "mdi:transmission-tower-import", period_key, init_imp
            )
            entities.append(s2)

            # 3. Exported Energy
            s3 = SolarSavingsEnergyAccumulator(
                hass, entry.entry_id, f"{period_name} Exported Energy", f"{period_key}_exported_energy", 
                exp_entity, "mdi:transmission-tower-export", period_key, init_exp
            )
            entities.append(s3)

            # 4. Self Consumed Energy
            s4 = SolarSavingsSelfConsumptionSensor(
                hass, entry.entry_id, f"{period_name} Self Consumed Energy", f"{period_key}_self_consumed",
                gen_entity, exp_entity, period_key, init_self
            )
            entities.append(s4)

            # 5. Import Cost ($)
            s5 = SolarSavingsFinancialAccumulator(
                hass, entry.entry_id, f"{period_name} Import Cost", f"{period_key}_import_cost",
                imp_entity, active_schedule, on_peak, off_peak, 0.0, "import", period_key, init_imp_cost
            )
            entities.append(s5)

            # 6. Export Credit ($)
            s6 = SolarSavingsFinancialAccumulator(
                hass, entry.entry_id, f"{period_name} Export Credit", f"{period_key}_export_credit",
                exp_entity, active_schedule, on_peak, off_peak, export_rate, "export", period_key, init_exp_credit
            )
            entities.append(s6)

            # 7. Solar Savings ($)
            s7 = SolarSavingsSavingsAccumulator(
                hass, entry.entry_id, f"{period_name} Solar Savings", f"{period_key}_solar_savings",
                gen_entity, exp_entity, active_schedule, on_peak, off_peak, export_rate, period_key, init_savings
            )
            entities.append(s7)

            # 8. Self Consumption Savings ($)
            s8 = SolarSavingsSelfConsumptionFinancialAccumulator(
                hass, entry.entry_id, f"{period_name} Self Consumption Savings", f"{period_key}_self_consumption_savings",
                gen_entity, exp_entity, active_schedule, on_peak, off_peak, period_key, init_self_savings
            )
            entities.append(s8)

            # --- Create Derived Sensors (Yesterday & Rolling 30) for Daily metrics ---
            if period_key == "daily":
                daily_sensors = [s1, s2, s3, s4, s5, s6, s7, s8]
                for parent in daily_sensors:
                    # Create Yesterday Sensor
                    y_name = parent.name.replace("Daily", "Yesterday")
                    y_id = parent.unique_id.replace("daily_", "yesterday_")
                    y_sensor = SolarSavingsHistorySensor(hass, entry.entry_id, y_name, y_id, parent, "yesterday")
                    entities.append(y_sensor)
                    parent.add_subscriber(y_sensor)

                    # Create Rolling 30 Day Sensor
                    r_name = parent.name.replace("Daily", "Last 30 Days")
                    r_id = parent.unique_id.replace("daily_", "rolling_30_day_")
                    r_sensor = SolarSavingsHistorySensor(hass, entry.entry_id, r_name, r_id, parent, "rolling_30")
                    entities.append(r_sensor)
                    parent.add_subscriber(r_sensor)

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


# --- History Sensor ---
class SolarSavingsHistorySensor(SensorEntity):
    """Sensor that displays history (Yesterday or Rolling 30 Day) from a Daily parent."""
    _attr_has_entity_name = True

    def __init__(self, hass, entry_id, name, unique_id, parent_sensor, mode):
        self.hass = hass
        self._entry_id = entry_id
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._parent = parent_sensor
        self._mode = mode # 'yesterday' or 'rolling_30'
        self._attr_native_value = 0.0
        
        # Inherit unit and class from parent
        self._attr_device_class = parent_sensor.device_class
        self._attr_native_unit_of_measurement = parent_sensor.native_unit_of_measurement
        self._attr_suggested_display_precision = parent_sensor.suggested_display_precision
        self._attr_icon = parent_sensor.icon.replace("calendar-today", "calendar-arrow-left") if parent_sensor.icon else "mdi:history"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Solar Savings",
            manufacturer="Solar Savings Integration",
            model="Savings Calculator",
        )

    async def async_added_to_hass(self) -> None:
        """Handle startup."""
        await super().async_added_to_hass()
        # Initialize with current data from parent
        if hasattr(self._parent, "get_daily_history"):
             self.update_from_history(self._parent.get_daily_history())

    @callback
    def update_from_history(self, history_list):
        """Called by parent when history updates."""
        if not history_list:
            self._attr_native_value = 0.0
        elif self._mode == "yesterday":
            self._attr_native_value = history_list[-1]
        elif self._mode == "rolling_30":
            self._attr_native_value = sum(history_list)
        
        # Safe update check
        if self.entity_id:
            self.async_write_ha_state()

# --- Base Class for Accumulators ---
class SolarSavingsAccumulator(RestoreSensor):
    """Base class for sensors that accumulate values over time, ignoring previous history."""
    
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL
    
    def __init__(self, hass, entry_id, name, unique_suffix, source_entity_id, icon, period, initial_value=0.0):
        self.hass = hass
        self._entry_id = entry_id
        self._source_entity_id = source_entity_id
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        self._attr_icon = icon
        self._period = period # total, daily, monthly, yearly
        self._initial_value = initial_value
        self._attr_native_value = 0.0 
        self._accumulated_delta = 0.0 # Tracks what this sensor has measured itself
        self._last_source_value = None
        self._last_reset = dt_util.now()
        
        # History Tracking
        self._daily_history = [] # Stores last 30 days of totals
        self._subscribers = []

    def add_subscriber(self, sensor):
        self._subscribers.append(sensor)
    
    def get_daily_history(self):
        return self._daily_history

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Solar Savings",
            manufacturer="Solar Savings Integration",
            model="Savings Calculator",
        )
    
    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = {
            "last_reset": self._last_reset.isoformat(),
            "initial_offset": self._initial_value,
            "accumulated_delta": self._accumulated_delta
        }
        if self._period == "daily":
            attrs["daily_history"] = self._daily_history
        return attrs

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # 1. Restore previous state
        state = await self.async_get_last_state()
        if state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                if "accumulated_delta" in state.attributes:
                    self._accumulated_delta = float(state.attributes["accumulated_delta"])
                else:
                    self._accumulated_delta = float(state.state)

                if "last_reset" in state.attributes:
                    self._last_reset = dt_util.parse_datetime(state.attributes["last_reset"])
                
                if "daily_history" in state.attributes:
                    self._daily_history = state.attributes["daily_history"]
                    
            except ValueError:
                self._accumulated_delta = 0.0
        
        # Initialize subscribers (but don't force write state if they aren't added yet)
        if self._period == "daily":
             # We rely on subscribers pulling data in THEIR async_added_to_hass
             # But if we updated right now (reset check below), we need to push.
             
             # Add midnight check for Daily sensors
            self.async_on_remove(
                async_track_time_change(self.hass, self._force_midnight_check, hour=0, minute=0, second=1)
            )

        # 2. Calculate Final Value
        self._attr_native_value = self._accumulated_delta + self._initial_value

        # Check for reset immediately on startup
        self._check_reset()

        # 3. Get current source value to start tracking deltas from NOW
        current_source = self.hass.states.get(self._source_entity_id)
        if current_source and current_source.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                self._last_source_value = float(current_source.state)
            except ValueError:
                self._last_source_value = None

        # 4. Listen for changes
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._source_entity_id], self._handle_state_change
            )
        )
    
    @callback
    def _force_midnight_check(self, now):
        """Forces a reset check at midnight."""
        self._check_reset()
        self.async_write_ha_state()

    def _check_reset(self):
        """Check if we need to reset based on period."""
        if self._period == "total":
            return

        now = dt_util.now()
        reset = False

        if self._period == "daily":
            if now.date() > self._last_reset.date():
                reset = True
        elif self._period == "monthly":
            if now.month != self._last_reset.month or now.year != self._last_reset.year:
                reset = True
        elif self._period == "yearly":
            if now.year != self._last_reset.year:
                reset = True
        
        if reset:
            # For Daily sensors, archive the history
            if self._period == "daily":
                # Ensure we archive the *current* state before resetting
                final_val = self._accumulated_delta + self._initial_value 
                
                self._daily_history.append(final_val)
                # Keep last 30 days
                if len(self._daily_history) > 30:
                    self._daily_history.pop(0)
                
                # Notify subscribers
                for sub in self._subscribers:
                    sub.update_from_history(self._daily_history)

            self._accumulated_delta = 0.0 # Reset tracked amount
            self._attr_native_value = self._initial_value if self._period == "total" else 0.0
            self._last_reset = now

    @callback
    def _handle_state_change(self, event):
        """Handle updates from the source entity."""
        # Check reset before processing new data
        self._check_reset()
        
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
            self.async_write_ha_state() 
            return

        # Calculate Delta
        delta = current_value - self._last_source_value
        
        # Ignore resets (negative delta) or tiny noise
        if delta < 0:
            self._last_source_value = current_value
            self.async_write_ha_state()
            return
            
        self._last_source_value = current_value
        self._process_delta(delta)
        
        # Update final state
        self._attr_native_value = self._accumulated_delta + self._initial_value
        self.async_write_ha_state()

    def _process_delta(self, delta):
        """Override this in subclasses to do specific math."""
        self._accumulated_delta += delta


# --- Specific Implementations ---

class SolarSavingsEnergyAccumulator(SolarSavingsAccumulator):
    """Tracks simple energy accumulation (kWh)."""
    
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(self, hass, entry_id, name, unique_suffix, source_entity_id, icon, period, initial_value=0.0):
        super().__init__(hass, entry_id, name, unique_suffix, source_entity_id, icon, period, initial_value)

    def _process_delta(self, delta):
        self._accumulated_delta += delta


class SolarSavingsFinancialAccumulator(SolarSavingsAccumulator):
    """Tracks financial costs/credits based on rates."""
    
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_suggested_display_precision = 2

    def __init__(self, hass, entry_id, name, unique_suffix, source_entity_id, 
                 schedule_id, on_peak, off_peak, export_rate, mode, period, initial_value=0.0):
        # Modes: "import" (costs money), "export" (makes money)
        super().__init__(hass, entry_id, name, unique_suffix, source_entity_id, "mdi:currency-usd", period, initial_value)
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
        self._accumulated_delta += cost_delta


class SolarSavingsSavingsAccumulator(RestoreSensor):
    """
    Complex logic: Tracks Total Savings.
    Savings = (Self Consumed * Import Rate) + (Exported * Export Rate)
    """
    
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:piggy-bank"

    def __init__(self, hass, entry_id, name, unique_suffix, 
                 gen_entity, exp_entity, schedule_id, on_peak, off_peak, export_rate, period, initial_value=0.0):
        self.hass = hass
        self._entry_id = entry_id
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        self._period = period
        self._initial_value = initial_value
        
        self._gen_entity = gen_entity
        self._exp_entity = exp_entity
        self._schedule_id = schedule_id
        self._on_peak = on_peak
        self._off_peak = off_peak
        self._export_rate = export_rate
        
        self._attr_native_value = 0.0
        self._accumulated_delta = 0.0
        self._attr_native_unit_of_measurement = hass.config.currency
        self._last_reset = dt_util.now()

        self._last_gen_val = None
        self._last_exp_val = None
        
        # History
        self._daily_history = []
        self._subscribers = []

    def add_subscriber(self, sensor):
        self._subscribers.append(sensor)
    
    def get_daily_history(self):
        return self._daily_history

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Solar Savings",
            manufacturer="Solar Savings Integration",
            model="Savings Calculator",
        )
    
    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = {
            "last_reset": self._last_reset.isoformat(),
            "initial_offset": self._initial_value,
            "accumulated_delta": self._accumulated_delta
        }
        if self._period == "daily":
            attrs["daily_history"] = self._daily_history
        return attrs

    async def async_added_to_hass(self) -> None:
        """Handle addition."""
        await super().async_added_to_hass()
        
        # Restore
        state = await self.async_get_last_state()
        if state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                if "accumulated_delta" in state.attributes:
                    self._accumulated_delta = float(state.attributes["accumulated_delta"])
                else:
                    self._accumulated_delta = float(state.state)

                if "last_reset" in state.attributes:
                    self._last_reset = dt_util.parse_datetime(state.attributes["last_reset"])
                
                if "daily_history" in state.attributes:
                    self._daily_history = state.attributes["daily_history"]
            except ValueError:
                self._accumulated_delta = 0.0
        
        # Update subscribers
        if self._period == "daily":
            self.async_on_remove(
                async_track_time_change(self.hass, self._force_midnight_check, hour=0, minute=0, second=1)
            )
        
        # Calculate
        self._attr_native_value = self._accumulated_delta + self._initial_value

        self._check_reset()

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

    @callback
    def _force_midnight_check(self, now):
        self._check_reset()
        self.async_write_ha_state()
    
    def _check_reset(self):
        """Check if we need to reset based on period."""
        if self._period == "total":
            return

        now = dt_util.now()
        reset = False

        if self._period == "daily":
            if now.date() > self._last_reset.date():
                reset = True
        elif self._period == "monthly":
            if now.month != self._last_reset.month or now.year != self._last_reset.year:
                reset = True
        elif self._period == "yearly":
            if now.year != self._last_reset.year:
                reset = True
        
        if reset:
            if self._period == "daily":
                final_val = self._accumulated_delta + self._initial_value
                self._daily_history.append(final_val)
                if len(self._daily_history) > 30:
                    self._daily_history.pop(0)
                for sub in self._subscribers:
                    sub.update_from_history(self._daily_history)

            self._accumulated_delta = 0.0
            self._attr_native_value = self._initial_value if self._period == "total" else 0.0
            self._last_reset = now

    @callback
    def _handle_change(self, event):
        self._check_reset()

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

        if entity_id == self._gen_entity:
            if self._last_gen_val is not None:
                delta = val - self._last_gen_val
                if delta > 0:
                    # Gen Delta contributes to savings assuming self-consumption initially
                    self._accumulated_delta += delta * import_rate_dollars
            self._last_gen_val = val

        elif entity_id == self._exp_entity:
            if self._last_exp_val is not None:
                delta = val - self._last_exp_val
                if delta > 0:
                    # Export Delta means it wasn't self consumed.
                    # Remove the Import Rate we added, and add Export Rate instead.
                    # Math: val += delta * (ExportRate - ImportRate)
                    correction = delta * (export_rate_dollars - import_rate_dollars)
                    self._accumulated_delta += correction
            self._last_exp_val = val
        
        self._attr_native_value = self._accumulated_delta + self._initial_value
        self.async_write_ha_state()


class SolarSavingsSelfConsumptionFinancialAccumulator(RestoreSensor):
    """
    Tracks Financial Savings from Self Consumption ONLY.
    Savings = (Self Consumed * Import Rate)
    """
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:piggy-bank-outline"

    def __init__(self, hass, entry_id, name, unique_suffix, 
                 gen_entity, exp_entity, schedule_id, on_peak, off_peak, period, initial_value=0.0):
        self.hass = hass
        self._entry_id = entry_id
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        self._period = period
        self._initial_value = initial_value
        
        self._gen_entity = gen_entity
        self._exp_entity = exp_entity
        self._schedule_id = schedule_id
        self._on_peak = on_peak
        self._off_peak = off_peak
        
        self._attr_native_value = 0.0
        self._accumulated_delta = 0.0
        self._attr_native_unit_of_measurement = hass.config.currency
        self._last_reset = dt_util.now()

        self._last_gen_val = None
        self._last_exp_val = None

        # History
        self._daily_history = []
        self._subscribers = []

    def add_subscriber(self, sensor):
        self._subscribers.append(sensor)
    
    def get_daily_history(self):
        return self._daily_history

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Solar Savings",
            manufacturer="Solar Savings Integration",
            model="Savings Calculator",
        )
    
    @property
    def extra_state_attributes(self):
        attrs = {
            "last_reset": self._last_reset.isoformat(),
            "initial_offset": self._initial_value,
            "accumulated_delta": self._accumulated_delta
        }
        if self._period == "daily":
            attrs["daily_history"] = self._daily_history
        return attrs

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                if "accumulated_delta" in state.attributes:
                    self._accumulated_delta = float(state.attributes["accumulated_delta"])
                else:
                    self._accumulated_delta = float(state.state)

                if "last_reset" in state.attributes:
                    self._last_reset = dt_util.parse_datetime(state.attributes["last_reset"])
                
                if "daily_history" in state.attributes:
                    self._daily_history = state.attributes["daily_history"]
            except ValueError:
                self._accumulated_delta = 0.0
        
        if self._period == "daily":
            self.async_on_remove(
                async_track_time_change(self.hass, self._force_midnight_check, hour=0, minute=0, second=1)
            )
        
        self._attr_native_value = self._accumulated_delta + self._initial_value
        self._check_reset()

        self._init_tracker(self._gen_entity, "_last_gen_val")
        self._init_tracker(self._exp_entity, "_last_exp_val")

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

    @callback
    def _force_midnight_check(self, now):
        self._check_reset()
        self.async_write_ha_state()

    def _check_reset(self):
        if self._period == "total": return
        now = dt_util.now()
        reset = False
        if self._period == "daily" and now.date() > self._last_reset.date(): reset = True
        elif self._period == "monthly" and (now.month != self._last_reset.month or now.year != self._last_reset.year): reset = True
        elif self._period == "yearly" and now.year != self._last_reset.year: reset = True
        
        if reset:
            if self._period == "daily":
                final_val = self._attr_native_value
                self._daily_history.append(final_val)
                if len(self._daily_history) > 30:
                    self._daily_history.pop(0)
                for sub in self._subscribers:
                    sub.update_from_history(self._daily_history)

            self._accumulated_delta = 0.0
            self._attr_native_value = self._initial_value if self._period == "total" else 0.0
            self._last_reset = now

    @callback
    def _handle_change(self, event):
        self._check_reset()
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        if not new_state or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE): return
        try:
            val = float(new_state.state)
        except ValueError: return

        import_rate_cents = get_current_import_rate_cents(
            self.hass, self._schedule_id, self._on_peak, self._off_peak
        )
        import_rate_dollars = import_rate_cents / 100.0

        if entity_id == self._gen_entity:
            if self._last_gen_val is not None:
                delta = val - self._last_gen_val
                if delta > 0:
                    self._accumulated_delta += delta * import_rate_dollars
            self._last_gen_val = val

        elif entity_id == self._exp_entity:
            if self._last_exp_val is not None:
                delta = val - self._last_exp_val
                if delta > 0:
                    self._accumulated_delta -= delta * import_rate_dollars
            self._last_exp_val = val
        
        self._attr_native_value = self._accumulated_delta + self._initial_value
        self.async_write_ha_state()


class SolarSavingsSelfConsumptionSensor(RestoreSensor):
    """Tracks Self Consumption Energy = Total Gen - Total Export."""
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:home-lightning-bolt"

    def __init__(self, hass, entry_id, name, unique_suffix, gen_entity_source, exp_entity_source, period, initial_value=0.0):
        self.hass = hass
        self._entry_id = entry_id
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        self._period = period
        self._initial_value = initial_value
        self._gen_entity = gen_entity_source
        self._exp_entity = exp_entity_source
        self._attr_native_value = 0.0
        self._accumulated_delta = 0.0
        self._last_gen = None
        self._last_exp = None
        self._last_reset = dt_util.now()

        # History
        self._daily_history = []
        self._subscribers = []

    def add_subscriber(self, sensor):
        self._subscribers.append(sensor)
    
    def get_daily_history(self):
        return self._daily_history

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Solar Savings",
            manufacturer="Solar Savings Integration",
            model="Savings Calculator",
        )

    @property
    def extra_state_attributes(self):
        attrs = {
            "last_reset": self._last_reset.isoformat(),
            "initial_offset": self._initial_value,
            "accumulated_delta": self._accumulated_delta
        }
        if self._period == "daily":
            attrs["daily_history"] = self._daily_history
        return attrs

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                if "accumulated_delta" in state.attributes:
                    self._accumulated_delta = float(state.attributes["accumulated_delta"])
                else:
                    self._accumulated_delta = float(state.state)

                if "last_reset" in state.attributes:
                    self._last_reset = dt_util.parse_datetime(state.attributes["last_reset"])

                if "daily_history" in state.attributes:
                    self._daily_history = state.attributes["daily_history"]
            except ValueError:
                self._accumulated_delta = 0.0
        
        if self._period == "daily":
            self.async_on_remove(
                async_track_time_change(self.hass, self._force_midnight_check, hour=0, minute=0, second=1)
            )
        
        self._attr_native_value = self._accumulated_delta + self._initial_value
        self._check_reset()
        
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

    @callback
    def _force_midnight_check(self, now):
        self._check_reset()
        self.async_write_ha_state()

    def _check_reset(self):
        if self._period == "total": return
        now = dt_util.now()
        reset = False
        if self._period == "daily" and now.date() > self._last_reset.date(): reset = True
        elif self._period == "monthly" and (now.month != self._last_reset.month or now.year != self._last_reset.year): reset = True
        elif self._period == "yearly" and now.year != self._last_reset.year: reset = True
        
        if reset:
            if self._period == "daily":
                final_val = self._attr_native_value
                self._daily_history.append(final_val)
                if len(self._daily_history) > 30:
                    self._daily_history.pop(0)
                for sub in self._subscribers:
                    sub.update_from_history(self._daily_history)

            self._accumulated_delta = 0.0
            self._attr_native_value = self._initial_value if self._period == "total" else 0.0
            self._last_reset = now

    @callback
    def _handle_change(self, event):
        self._check_reset()
        eid = event.data.get("entity_id")
        new_s = event.data.get("new_state")
        if not new_s or new_s.state in (STATE_UNKNOWN, STATE_UNAVAILABLE): return
        try:
            val = float(new_s.state)
        except ValueError: return

        if eid == self._gen_entity:
            if self._last_gen is not None:
                d = val - self._last_gen
                if d > 0: self._accumulated_delta += d
            self._last_gen = val
        elif eid == self._exp_entity:
            if self._last_exp is not None:
                d = val - self._last_exp
                if d > 0: self._accumulated_delta -= d # Export reduces self consumption
            self._last_exp = val
        
        self._attr_native_value = self._accumulated_delta + self._initial_value
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