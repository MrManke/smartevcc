"""Switch platform for SmartEVCC."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .ems import SmartEVCCEMS

_LOGGER = logging.getLogger(__name__)

FORCE_CHARGE_SWITCH = SwitchEntityDescription(
    key="force_charge",
    name="SmartEVCC Force Charge",
    icon="mdi:lightning-bolt",
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SmartEVCC switch platform."""
    ems: SmartEVCCEMS = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SmartEVCCForceSwitch(ems, FORCE_CHARGE_SWITCH)])


class SmartEVCCForceSwitch(RestoreEntity, SwitchEntity):
    """Representation of the SmartEVCC Force Charge switch."""

    def __init__(self, ems: SmartEVCCEMS, description: SwitchEntityDescription) -> None:
        """Initialize the switch."""
        self.ems = ems
        self.entity_description = description
        
        self._attr_unique_id = f"{ems.config_entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, ems.config_entry.entry_id)},
            name="SmartEVCC Controller",
            manufacturer="SmartEVCC",
            model="Local EMS",
        )
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        """Restore previous state."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        
        if last_state is not None:
             self._attr_is_on = last_state.state == "on"

        self.ems.force_charge = self._attr_is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        self._attr_is_on = True
        self.async_write_ha_state()
        self.ems.force_charge = True
        
        _LOGGER.info("SmartEVCC Force Charge turned ON. Triggering Slow Loop re-evaluation.")
        from datetime import datetime
        self.hass.async_create_task(self.ems._slow_loop_tick(datetime.now()))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        self._attr_is_on = False
        self.async_write_ha_state()
        self.ems.force_charge = False
        
        _LOGGER.info("SmartEVCC Force Charge turned OFF. Triggering Slow Loop re-evaluation.")
        from datetime import datetime
        self.hass.async_create_task(self.ems._slow_loop_tick(datetime.now()))
