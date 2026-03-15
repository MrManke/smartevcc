"""Number platform for SmartEVCC."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .ems import SmartEVCCEMS

_LOGGER = logging.getLogger(__name__)

NUMBERS: tuple[NumberEntityDescription, ...] = (
    NumberEntityDescription(
        key="max_price_limit",
        name="SmartEVCC Max Price Limit",
        icon="mdi:cash-remove",
        native_min_value=-10.0,
        native_max_value=10.0,
        native_step=0.01,
        native_unit_of_measurement="SEK/kWh",
    ),
    NumberEntityDescription(
        key="low_price_charging_limit",
        name="SmartEVCC Low Price Limit",
        icon="mdi:cash-plus",
        native_min_value=-10.0,
        native_max_value=10.0,
        native_step=0.01,
        native_unit_of_measurement="SEK/kWh",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SmartEVCC number platform."""
    ems: SmartEVCCEMS = hass.data[DOMAIN][entry.entry_id]
    
    entities = [SmartEVCCNumber(ems, description) for description in NUMBERS]
    async_add_entities(entities)


class SmartEVCCNumber(RestoreEntity, NumberEntity):
    """Representation of a SmartEVCC Number modifier."""

    def __init__(self, ems: SmartEVCCEMS, description: NumberEntityDescription) -> None:
        """Initialize the number entity."""
        self.ems = ems
        self.entity_description = description
        
        self._attr_unique_id = f"{ems.config_entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, ems.config_entry.entry_id)},
            name="SmartEVCC Controller",
            manufacturer="SmartEVCC",
            model="Local EMS",
        )
        self._attr_native_value = 0.0

    async def async_added_to_hass(self) -> None:
        """Restore state and subscribe to data updates."""
        await super().async_added_to_hass()
        
        # Restore previous state
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in ("unknown", "unavailable"):
            try:
                self._attr_native_value = float(last_state.state)
            except ValueError:
                pass
                
        # Update EMS property with this instance so EMS can access the value directly, or set initial value
        setattr(self.ems, self.entity_description.key, self._attr_native_value)

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        self._attr_native_value = value
        self.async_write_ha_state()

        # Update EMS Memory
        setattr(self.ems, self.entity_description.key, value)
        
        _LOGGER.info("SmartEVCC %s limit changed to %s. Triggering Slow Loop re-evaluation.", self.entity_description.key, value)
        # Manually tick the slow loop to instantly apply the new limit
        from datetime import datetime
        self.hass.async_create_task(self.ems._slow_loop_tick(datetime.now()))
