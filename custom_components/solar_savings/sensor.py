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
from homeassistant.util import dt as dt_util

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
            
            # 1. Generated Energy
            entities.append(SolarSavingsEnergyAccumulator(
                hass, entry.entry_id, f"{period_name} Generated Energy", f"{period_key}_generated_energy", 
                gen_entity, "mdi:solar-power", period_key
            ))

            # 2. Imported Energy
            entities.append(SolarSavingsEnergyAccumulator(
                hass, entry.entry_id, f"{period_name} Imported Energy", f"{period_key}_imported_energy", 
                imp_entity, "mdi:transmission-tower-import", period_key
            ))

            # 3. Exported Energy
            entities.append(SolarSavingsEnergyAccumulator(
                hass, entry.entry_id, f"{period_name} Exported Energy", f"{period_key}_exported_energy", 
                exp_entity, "mdi:transmission-tower-export", period_key
            ))

            # 4. Self Consumed Energy
            entities.append(SolarSavingsSelfConsumptionSensor(
                hass, entry.entry_id, f"{period_name} Self Consumed Energy", f"{period_key}_self_consumed",
                gen_entity, exp_entity, period_key
            ))

            # 5. Import Cost ($)
            entities.append(SolarSavingsFinancialAccumulator(
                hass, entry.entry_id, f"{period_name} Import Cost", f"{period_key}_import_cost",
                imp_entity, active_schedule, on_peak, off_peak, 0.0, "import", period_key
            ))

            # 6. Export Credit ($)
            entities.append(SolarSavingsFinancialAccumulator(
                hass, entry.entry_id, f"{period_name} Export Credit", f"{period_key}_export_credit",
                exp_entity, active_schedule, on_peak, off_peak, export_rate, "export", period_key
            ))

            # 7. Solar Savings ($)
            entities.append(SolarSavingsSavingsAccumulator(
                hass, entry.entry_id, f"{period_name} Solar Savings", f"{period_key}_solar_savings",
                gen_entity, exp_entity, active_schedule, on_peak, off_peak, export_rate, period_key
            ))

            # 8. Self Consumption Savings ($)
            entities.append(SolarSavingsSelfConsumptionFinancialAccumulator(
                hass, entry.entry_id, f"{period_name} Self Consumption Savings", f"{period_key}_self_consumption_savings",
                gen_entity, exp_entity, active_schedule, on_peak, off_peak, period_key
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
    
    def __init__(self, hass, entry_id, name, unique_suffix, source_entity_id, icon, period):
        self.hass = hass
        self._entry_id = entry_id
        self._source_entity_id = source_entity_id
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        self._attr_icon = icon
        self._attr_native_value = 0.0
        self._period = period # total, daily, monthly, yearly
        self._last_source_value = None
        self._last_reset = dt_util.now()

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
        return {
            "last_reset": self._last_reset.isoformat()
        }

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # 1. Restore previous accumulated value
        state = await self.async_get_last_state()
        if state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                self._attr_native_value = float(state.state)
                # Restore last reset date
                if "last_reset" in state.attributes:
                    self._last_reset = dt_util.parse_datetime(state.attributes["last_reset"])
            except ValueError:
                self._attr_native_value = 0.0

        # Check for reset immediately on startup
        self._check_reset()

        # 2. Get current source value to start tracking deltas from NOW
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
            self._attr_native_value = 0.0
            self._last_reset = now

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
            # Don't return, we update state to save the reset if needed
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

    def __init__(self, hass, entry_id, name, unique_suffix, source_entity_id, icon, period):
        super().__init__(hass, entry_id, name, unique_suffix, source_entity_id, icon, period)

    def _process_delta(self, delta):
        self._attr_native_value += delta


class SolarSavingsFinancialAccumulator(SolarSavingsAccumulator):
    """Tracks financial costs/credits based on rates."""
    
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_suggested_display_precision = 2

    def __init__(self, hass, entry_id, name, unique_suffix, source_entity_id, 
                 schedule_id, on_peak, off_peak, export_rate, mode, period):
        # Modes: "import" (costs money), "export" (makes money)
        super().__init__(hass, entry_id, name, unique_suffix, source_entity_id, "mdi:currency-usd", period)
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
    """
    
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:piggy-bank"

    def __init__(self, hass, entry_id, name, unique_suffix, 
                 gen_entity, exp_entity, schedule_id, on_peak, off_peak, export_rate, period):
        self.hass = hass
        self._entry_id = entry_id
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        self._period = period
        
        self._gen_entity = gen_entity
        self._exp_entity = exp_entity
        self._schedule_id = schedule_id
        self._on_peak = on_peak
        self._off_peak = off_peak
        self._export_rate = export_rate
        
        self._attr_native_value = 0.0
        self._attr_native_unit_of_measurement = hass.config.currency
        self._last_reset = dt_util.now()

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
    
    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            "last_reset": self._last_reset.isoformat()
        }

    async def async_added_to_hass(self) -> None:
        """Handle addition."""
        await super().async_added_to_hass()
        
        # Restore
        state = await self.async_get_last_state()
        if state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                self._attr_native_value = float(state.state)
                if "last_reset" in state.attributes:
                    self._last_reset = dt_util.parse_datetime(state.attributes["last_reset"])
            except ValueError:
                self._attr_native_value = 0.0
        
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
            self._attr_native_value = 0.0
            self._last_reset = now

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
                 gen_entity, exp_entity, schedule_id, on_peak, off_peak, period):
        self.hass = hass
        self._entry_id = entry_id
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        self._period = period
        
        self._gen_entity = gen_entity
        self._exp_entity = exp_entity
        self._schedule_id = schedule_id
        self._on_peak = on_peak
        self._off_peak = off_peak
        
        self._attr_native_value = 0.0
        self._attr_native_unit_of_measurement = hass.config.currency
        self._last_reset = dt_util.now()

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
    
    @property
    def extra_state_attributes(self):
        return {"last_reset": self._last_reset.isoformat()}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                self._attr_native_value = float(state.state)
                if "last_reset" in state.attributes:
                    self._last_reset = dt_util.parse_datetime(state.attributes["last_reset"])
            except ValueError:
                self._attr_native_value = 0.0
        
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

    def _check_reset(self):
        if self._period == "total": return
        now = dt_util.now()
        reset = False
        if self._period == "daily" and now.date() > self._last_reset.date(): reset = True
        elif self._period == "monthly" and (now.month != self._last_reset.month or now.year != self._last_reset.year): reset = True
        elif self._period == "yearly" and now.year != self._last_reset.year: reset = True
        
        if reset:
            self._attr_native_value = 0.0
            self._last_reset = now

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
                    self._attr_native_value += delta * import_rate_dollars
            self._last_gen_val = val

        elif entity_id == self._exp_entity:
            if self._last_exp_val is not None:
                delta = val - self._last_exp_val
                if delta > 0:
                    self._attr_native_value -= delta * import_rate_dollars
            self._last_exp_val = val
        
        self.async_write_ha_state()


class SolarSavingsSelfConsumptionSensor(RestoreSensor):
    """Tracks Self Consumption Energy = Total Gen - Total Export."""
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:home-lightning-bolt"

    def __init__(self, hass, entry_id, name, unique_suffix, gen_entity_source, exp_entity_source, period):
        self.hass = hass
        self._entry_id = entry_id
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        self._period = period
        self._gen_entity = gen_entity_source
        self._exp_entity = exp_entity_source
        self._attr_native_value = 0.0
        self._last_gen = None
        self._last_exp = None
        self._last_reset = dt_util.now()

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
        return {"last_reset": self._last_reset.isoformat()}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                self._attr_native_value = float(state.state)
                if "last_reset" in state.attributes:
                    self._last_reset = dt_util.parse_datetime(state.attributes["last_reset"])
            except ValueError:
                self._attr_native_value = 0.0
        
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

    def _check_reset(self):
        if self._period == "total": return
        now = dt_util.now()
        reset = False
        if self._period == "daily" and now.date() > self._last_reset.date(): reset = True
        elif self._period == "monthly" and (now.month != self._last_reset.month or now.year != self._last_reset.year): reset = True
        elif self._period == "yearly" and now.year != self._last_reset.year: reset = True
        
        if reset:
            self._attr_native_value = 0.0
            self._last_reset = now

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