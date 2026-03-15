"""Constants for the SmartEVCC integration."""

DOMAIN = "smartevcc"

CONF_MAIN_FUSE = "main_fuse"
CONF_P1_PHASE_1 = "p1_phase_1"
CONF_P1_PHASE_2 = "p1_phase_2"
CONF_P1_PHASE_3 = "p1_phase_3"
CONF_CHARGER_CONTROL_ENTITY = "charger_control_entity"
CONF_CHARGER_STATUS_ENTITY = "charger_status_entity"
CONF_ZAPTEC_PHASE_ENTITY = "zaptec_phase_entity"

# Slow Loop Configs
CONF_NORDPOOL_ENTITY = "nordpool_entity"
CONF_EV_BATTERY_LEVEL = "ev_battery_level"
CONF_EV_MIN_SOC = "ev_min_soc"
CONF_EV_TARGET_LEVEL = "ev_target_level"
CONF_EV_BATTERY_CAPACITY = "ev_battery_capacity"
CONF_EV_MAX_CHARGE_RATE = "ev_max_charge_rate"
CONF_EV_TEMP_SENSOR = "ev_temp_sensor"
CONF_EV_COLD_TEMP_THRESHOLD = "ev_cold_temp_threshold"
CONF_EV_COLD_CHARGE_RATE = "ev_cold_charge_rate"
CONF_DEPARTURE_TIME = "departure_time"
CONF_RECOVERY_DURATION = "recovery_duration"

CONF_DEBUG_MODE = "debug_mode"
CONF_ENABLE_LOAD_SHEDDING = "enable_load_shedding"
CONF_SHEDDING_LEVEL_1_SWITCHES = "shedding_level_1_switches"
CONF_SHEDDING_LEVEL_2_SWITCHES = "shedding_level_2_switches"
CONF_SHEDDING_CLIMATES = "shedding_climates"
CONF_SPIKE_OVERRIDE = "spike_override"
CONF_PHASE_BALANCING = "phase_balancing"

DEFAULT_MAIN_FUSE = 16.0
DEFAULT_DEBUG_MODE = False
DEFAULT_ENABLE_LOAD_SHEDDING = False
DEFAULT_SPIKE_OVERRIDE = False
DEFAULT_PHASE_BALANCING = False

# Slow Loop Defaults
DEFAULT_EV_MIN_SOC = 20
DEFAULT_EV_TARGET_LEVEL = 80
DEFAULT_EV_BATTERY_CAPACITY = 77.0
DEFAULT_EV_MAX_CHARGE_RATE = 11.0
DEFAULT_EV_COLD_TEMP_THRESHOLD = -4.0
DEFAULT_EV_COLD_CHARGE_RATE = 4.0
DEFAULT_DEPARTURE_TIME = "07:00"
DEFAULT_RECOVERY_DURATION = 60.0

DEFAULT_MAIN_FUSE = 16.0
DEFAULT_DEBUG_MODE = False
DEFAULT_ENABLE_LOAD_SHEDDING = False

