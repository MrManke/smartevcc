"""Config flow for SmartEVCC integration."""
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
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
    CONF_ENABLE_LOAD_SHEDDING,
    CONF_MAIN_FUSE,
    CONF_P1_PHASE_1,
    CONF_P1_PHASE_2,
    CONF_P1_PHASE_3,
    CONF_SHEDDING_CLIMATES,
    CONF_SHEDDING_LEVEL_1_SWITCHES,
    CONF_SHEDDING_LEVEL_2_SWITCHES,
    DEFAULT_DEBUG_MODE,
    DEFAULT_ENABLE_LOAD_SHEDDING,
    DEFAULT_MAIN_FUSE,
    DOMAIN,
)

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
                    min=10, max=63, step=1, mode=NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_P1_PHASE_1, default=data.get(CONF_P1_PHASE_1, vol.UNDEFINED)
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_P1_PHASE_2, default=data.get(CONF_P1_PHASE_2, vol.UNDEFINED)
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_P1_PHASE_3, default=data.get(CONF_P1_PHASE_3, vol.UNDEFINED)
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_CHARGER_CONTROL_ENTITY,
                default=data.get(CONF_CHARGER_CONTROL_ENTITY, vol.UNDEFINED),
            ): EntitySelector(EntitySelectorConfig(domain="number")),
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
            vol.Optional(
                CONF_DEBUG_MODE,
                default=data.get(CONF_DEBUG_MODE, DEFAULT_DEBUG_MODE),
            ): BooleanSelector(),
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
        return SmartEVCCOptionsFlowHandler(config_entry)


class SmartEVCCOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle an options flow for SmartEVCC."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

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
            step_id="init", data_schema=_get_base_schema(current_config)
        )
