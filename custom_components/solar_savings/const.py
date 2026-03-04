"""Constants for the Solar Savings integration."""

DOMAIN = "solar_savings"

# Config Keys
CONF_PEAK_SCHEDULE = "peak_schedule"
CONF_ON_PEAK_RATE = "on_peak_rate"
CONF_OFF_PEAK_RATE = "off_peak_rate"
CONF_EXPORT_RATE = "export_rate"

# New Input Entities
CONF_SOLAR_GENERATION_ENTITY = "solar_generation_entity"
CONF_GRID_IMPORT_ENTITY = "grid_import_entity"
CONF_GRID_EXPORT_ENTITY = "grid_export_entity"

# ROI Inputs (Optional)
CONF_SYSTEM_COST = "system_cost"
CONF_PTO_DATE = "pto_date"

# Historical / Initial Values (Optional)
CONF_INITIAL_GENERATION = "initial_generation"
CONF_INITIAL_IMPORT = "initial_import"
CONF_INITIAL_EXPORT = "initial_export"
CONF_INITIAL_SELF_CONSUMED = "initial_self_consumed"

CONF_INITIAL_IMPORT_COST = "initial_import_cost"
CONF_INITIAL_EXPORT_CREDIT = "initial_export_credit"
CONF_INITIAL_SELF_CONSUMED_SAVINGS = "initial_self_consumed_savings"
CONF_INITIAL_SAVINGS = "initial_savings"

CONF_WIPE_DATA = "wipe_data"