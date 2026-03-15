"""Config flow for SmartEVCC integration."""
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_CHARGER_CONTROL_ENTITY,
    CONF_DEBUG_MODE,
    CONF_DEPARTURE_TIME,
    CONF_ENABLE_LOAD_SHEDDING,
    CONF_EV_BATTERY_CAPACITY,
    CONF_EV_BATTERY_LEVEL,
    CONF_EV_COLD_CHARGE_RATE,
    CONF_EV_COLD_TEMP_THRESHOLD,
    CONF_EV_MAX_CHARGE_RATE,
    CONF_EV_MIN_SOC,
    CONF_EV_TARGET_LEVEL,
    CONF_EV_TEMP_SENSOR,
    CONF_MAIN_FUSE,
    CONF_NORDPOOL_ENTITY,
    CONF_P1_PHASE_1,
    CONF_DEPARTURE_TIME,
    CONF_ENABLE_LOAD_SHEDDING,
    CONF_EV_BATTERY_CAPACITY,
    CONF_EV_BATTERY_LEVEL,
    CONF_EV_COLD_CHARGE_RATE,
    CONF_EV_COLD_TEMP_THRESHOLD,
    CONF_EV_MAX_CHARGE_RATE,
    CONF_EV_MIN_SOC,
    CONF_EV_TARGET_LEVEL,
    CONF_EV_TEMP_SENSOR,
    CONF_MAIN_FUSE,
    CONF_NORDPOOL_ENTITY,
    CONF_P1_PHASE_1,
    CONF_P1_PHASE_2,
    CONF_P1_PHASE_3,
    CONF_SHEDDING_CLIMATES,
    CONF_SHEDDING_LEVEL_1_SWITCHES,
    CONF_SHEDDING_LEVEL_2_SWITCHES,
    CONF_CHARGER_STATUS_ENTITY,
    DEFAULT_DEBUG_MODE,
    DEFAULT_DEPARTURE_TIME,
    DEFAULT_ENABLE_LOAD_SHEDDING,
    DEFAULT_EV_BATTERY_CAPACITY,
    DEFAULT_EV_COLD_CHARGE_RATE,
    DEFAULT_EV_COLD_TEMP_THRESHOLD,
    DEFAULT_EV_MAX_CHARGE_RATE,
    DEFAULT_EV_MIN_SOC,
    DEFAULT_EV_TARGET_LEVEL,
    DEFAULT_MAIN_FUSE,
    DOMAIN,
)
import homeassistant.helpers.selector as selector

def _get_base_schema(data: dict[str, Any] | None = None) -> vol.Schema:
    """Return the base schema with current or default values."""
    if data is None:
        data = {}

    return vol.Schema(
        {
            vol.Required(
                CONF_MAIN_FUSE, default=data.get(CONF_MAIN_FUSE, DEFAULT_MAIN_FUSE)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=10.0, max=63.0, step=1.0, mode=NumberSelectorMode.SLIDER
                )
            ),
            vol.Required(
                CONF_P1_PHASE_1, default=data.get(CONF_P1_PHASE_1, vol.UNDEFINED)
            ): EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.CURRENT)),
            vol.Required(
                CONF_P1_PHASE_2, default=data.get(CONF_P1_PHASE_2, vol.UNDEFINED)
            ): EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.CURRENT)),
            vol.Required(
                CONF_P1_PHASE_3, default=data.get(CONF_P1_PHASE_3, vol.UNDEFINED)
            ): EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.CURRENT)),
            vol.Required(
                CONF_CHARGER_CONTROL_ENTITY,
                default=data.get(CONF_CHARGER_CONTROL_ENTITY, vol.UNDEFINED),
            ): EntitySelector(EntitySelectorConfig(domain="number")),
            
            # Phase 4: Nordpool & EV Planner Configs
            vol.Required(
                CONF_NORDPOOL_ENTITY, default=data.get(CONF_NORDPOOL_ENTITY, vol.UNDEFINED)
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_EV_BATTERY_LEVEL, default=data.get(CONF_EV_BATTERY_LEVEL, vol.UNDEFINED)
            ): EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.BATTERY)),
            vol.Required(
                CONF_EV_MIN_SOC, default=data.get(CONF_EV_MIN_SOC, DEFAULT_EV_MIN_SOC)
            ): NumberSelector(NumberSelectorConfig(min=0, max=100, step=1, mode=NumberSelectorMode.SLIDER)),
            vol.Required(
                CONF_EV_TARGET_LEVEL, default=data.get(CONF_EV_TARGET_LEVEL, DEFAULT_EV_TARGET_LEVEL)
            ): NumberSelector(NumberSelectorConfig(min=0, max=100, step=1, mode=NumberSelectorMode.SLIDER)),
            vol.Required(
                CONF_EV_BATTERY_CAPACITY, default=data.get(CONF_EV_BATTERY_CAPACITY, DEFAULT_EV_BATTERY_CAPACITY)
            ): NumberSelector(NumberSelectorConfig(min=10.0, max=200.0, step=1.0, mode=NumberSelectorMode.SLIDER)),
            vol.Required(
                CONF_EV_MAX_CHARGE_RATE, default=data.get(CONF_EV_MAX_CHARGE_RATE, DEFAULT_EV_MAX_CHARGE_RATE)
            ): NumberSelector(NumberSelectorConfig(min=1.0, max=22.0, step=0.1, mode=NumberSelectorMode.SLIDER)),
            vol.Required(
                CONF_EV_TEMP_SENSOR, default=data.get(CONF_EV_TEMP_SENSOR, vol.UNDEFINED)
            ): EntitySelector(EntitySelectorConfig(domain=["sensor", "weather"], device_class=SensorDeviceClass.TEMPERATURE)),
            vol.Required(
                CONF_EV_COLD_TEMP_THRESHOLD, default=data.get(CONF_EV_COLD_TEMP_THRESHOLD, DEFAULT_EV_COLD_TEMP_THRESHOLD)
            ): NumberSelector(NumberSelectorConfig(min=-30.0, max=20.0, step=1.0, mode=NumberSelectorMode.SLIDER)),
            vol.Required(
                CONF_EV_COLD_CHARGE_RATE, default=data.get(CONF_EV_COLD_CHARGE_RATE, DEFAULT_EV_COLD_CHARGE_RATE)
            ): NumberSelector(NumberSelectorConfig(min=1.0, max=22.0, step=0.1, mode=NumberSelectorMode.SLIDER)),
            vol.Required(
                CONF_DEPARTURE_TIME, default=data.get(CONF_DEPARTURE_TIME, DEFAULT_DEPARTURE_TIME)
            ): selector.TimeSelector(),

            # Shedding settings
            vol.Optional(
                CONF_ENABLE_LOAD_SHEDDING,
                default=data.get(
                    CONF_ENABLE_LOAD_SHEDDING, DEFAULT_ENABLE_LOAD_SHEDDING
                ),
            ): BooleanSelector(),
            vol.Optional(
                CONF_SHEDDING_LEVEL_1_SWITCHES,
                default=data.get(CONF_SHEDDING_LEVEL_1_SWITCHES, []),
            ): EntitySelector(
                EntitySelectorConfig(domain=["switch", "input_boolean"], multiple=True)
            ),
            vol.Optional(
                CONF_SHEDDING_LEVEL_2_SWITCHES,
                default=data.get(CONF_SHEDDING_LEVEL_2_SWITCHES, []),
            ): EntitySelector(
                EntitySelectorConfig(domain=["switch", "input_boolean"], multiple=True)
            ),
            vol.Optional(
                CONF_SHEDDING_CLIMATES, default=data.get(CONF_SHEDDING_CLIMATES, [])
            ): EntitySelector(EntitySelectorConfig(domain="climate", multiple=True)),
        }
    )


def _get_options_schema(data: dict[str, Any] | None = None) -> vol.Schema:
    """Return the options schema, stripping out entities now handled by UI (numbers, toggle)."""
    if data is None:
        data = {}

    return vol.Schema(
        {
            vol.Required(
                CONF_P1_PHASE_1, default=data.get(CONF_P1_PHASE_1, vol.UNDEFINED)
            ): EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.CURRENT)),
            vol.Required(
                CONF_P1_PHASE_2, default=data.get(CONF_P1_PHASE_2, vol.UNDEFINED)
            ): EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.CURRENT)),
            vol.Required(
                CONF_P1_PHASE_3, default=data.get(CONF_P1_PHASE_3, vol.UNDEFINED)
            ): EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.CURRENT)),
            vol.Required(
                CONF_CHARGER_CONTROL_ENTITY,
                default=data.get(CONF_CHARGER_CONTROL_ENTITY, vol.UNDEFINED),
            ): EntitySelector(EntitySelectorConfig(domain="number")),
            
            # Phase 4: Nordpool & EV Planner Configs
            vol.Required(
                CONF_NORDPOOL_ENTITY, default=data.get(CONF_NORDPOOL_ENTITY, vol.UNDEFINED)
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_EV_BATTERY_LEVEL, default=data.get(CONF_EV_BATTERY_LEVEL, vol.UNDEFINED)
            ): EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.BATTERY)),
            vol.Required(
                CONF_EV_TEMP_SENSOR, default=data.get(CONF_EV_TEMP_SENSOR, vol.UNDEFINED)
            ): EntitySelector(EntitySelectorConfig(domain=["sensor", "weather"], device_class=SensorDeviceClass.TEMPERATURE)),
            vol.Required(
                CONF_DEPARTURE_TIME, default=data.get(CONF_DEPARTURE_TIME, DEFAULT_DEPARTURE_TIME)
            ): selector.TimeSelector(),

            # Shedding settings
            vol.Optional(
                CONF_SHEDDING_LEVEL_1_SWITCHES,
                default=data.get(CONF_SHEDDING_LEVEL_1_SWITCHES, []),
            ): EntitySelector(
                EntitySelectorConfig(domain=["switch", "input_boolean"], multiple=True)
            ),
            vol.Optional(
                CONF_SHEDDING_LEVEL_2_SWITCHES,
                default=data.get(CONF_SHEDDING_LEVEL_2_SWITCHES, []),
            ): EntitySelector(
                EntitySelectorConfig(domain=["switch", "input_boolean"], multiple=True)
            ),
            vol.Optional(
                CONF_SHEDDING_CLIMATES, default=data.get(CONF_SHEDDING_CLIMATES, [])
            ): EntitySelector(EntitySelectorConfig(domain="climate", multiple=True)),
        }
    )

class SmartEVCCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SmartEVCC."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(title="SmartEVCC", data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=_get_base_schema(), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return SmartEVCCOptionsFlowHandler()


class SmartEVCCOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle an options flow for SmartEVCC."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # We save ALL settings into options, overriding data on reload
            return self.async_create_entry(title="", data=user_input)

        # Merge data and options so the form reflects the current state
        current_config = dict(self.config_entry.data)
        current_config.update(self.config_entry.options)

        return self.async_show_form(
            step_id="init", data_schema=_get_options_schema(current_config)
        )
