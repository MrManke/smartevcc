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
        name="Maxpris laddning",
        icon="mdi:cash-remove",
        native_min_value=-10.0,
        native_max_value=10.0,
        native_step=0.01,
        native_unit_of_measurement="SEK/kWh",
    ),
    NumberEntityDescription(
        key="low_price_charging_limit",
        name="Tröskel för billigt pris",
        icon="mdi:cash-plus",
        native_min_value=-10.0,
        native_max_value=10.0,
        native_step=0.01,
        native_unit_of_measurement="SEK/kWh",
    ),
    NumberEntityDescription(
        key="main_fuse",
        name="Huvudsäkring",
        icon="mdi:fuse",
        native_min_value=10.0,
        native_max_value=63.0,
        native_step=1.0,
        native_unit_of_measurement="A",
    ),
    NumberEntityDescription(
        key="ev_min_soc",
        name="Nödladdning (Min SoC)",
        icon="mdi:battery-alert",
        native_min_value=0.0,
        native_max_value=100.0,
        native_step=1.0,
        native_unit_of_measurement="%",
    ),
    NumberEntityDescription(
        key="ev_target_level",
        name="Målnivå (Target SoC)",
        icon="mdi:battery-charging-100",
        native_min_value=0.0,
        native_max_value=100.0,
        native_step=1.0,
        native_unit_of_measurement="%",
    ),
    NumberEntityDescription(
        key="ev_battery_capacity",
        name="Batterikapacitet",
        icon="mdi:car-battery",
        native_min_value=10.0,
        native_max_value=200.0,
        native_step=1.0,
        native_unit_of_measurement="kWh",
    ),
    NumberEntityDescription(
        key="ev_max_charge_rate",
        name="Maximal Laddeffekt",
        icon="mdi:ev-station",
        native_min_value=1.0,
        native_max_value=22.0,
        native_step=0.1,
        native_unit_of_measurement="kW",
    ),
    NumberEntityDescription(
        key="ev_cold_temp_threshold",
        name="Köldgräns för lägre laddeffekt",
        icon="mdi:thermometer-minus",
        native_min_value=-30.0,
        native_max_value=20.0,
        native_step=1.0,
        native_unit_of_measurement="°C",
    ),
    NumberEntityDescription(
        key="ev_cold_charge_rate",
        name="Assumerad Laddeffekt vid extremkyla",
        icon="mdi:snowflake",
        native_min_value=1.0,
        native_max_value=22.0,
        native_step=0.1,
        native_unit_of_measurement="kW",
    ),
    NumberEntityDescription(
        key="recovery_duration",
        name="Väntetid för upprampning",
        icon="mdi:timer-sand",
        native_min_value=10.0,
        native_max_value=600.0,
        native_step=10.0,
        native_unit_of_measurement="s",
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
        self._attr_mode = "box"
        self._attr_native_value = 0.0

    async def async_added_to_hass(self) -> None:
        """Restore state and subscribe to data updates."""
        await super().async_added_to_hass()
        
        # Restore previous state or fetch from config
        last_state = await self.async_get_last_state()
        if last_state is None or (last_state and last_state.state in ("unknown", "unavailable")):
            opt = self.ems.config_entry.options.get(self.entity_description.key)
            if opt is not None:
                self._attr_native_value = float(opt)
            else:
                dat = self.ems.config_entry.data.get(self.entity_description.key)
                if dat is not None:
                    self._attr_native_value = float(dat)
        elif last_state is not None and last_state.state not in ("unknown", "unavailable"):
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
