"""Sensor platform for SmartEVCC."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .ems import SmartEVCCEMS

_LOGGER = logging.getLogger(__name__)

STATUS_SENSOR = SensorEntityDescription(
    key="smartevcc_status",
    name="Status",
    icon="mdi:ev-station",
)

LOWEST_TEMP_SENSOR = SensorEntityDescription(
    key="lowest_temp_forecast",
    name="Lägsta prognostiserade temperatur",
    icon="mdi:thermometer-minus",
    native_unit_of_measurement="°C",
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SmartEVCC sensor platform."""
    ems: SmartEVCCEMS = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        SmartEVCCStatusSensor(ems, STATUS_SENSOR),
        SmartEVCCWeatherForecastSensor(ems, LOWEST_TEMP_SENSOR),
    ])


class SmartEVCCStatusSensor(SensorEntity):
    """Representation of a SmartEVCC Status Sensor."""

    def __init__(self, ems: SmartEVCCEMS, description: SensorEntityDescription) -> None:
        """Initialize the sensor."""
        self.ems = ems
        self.entity_description = description
        
        # Unique ID matching the config entry and sensor key
        self._attr_unique_id = f"{ems.config_entry.entry_id}_{description.key}"
        
        # Tie this sensor to a pseudo-device for SmartEVCC
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, ems.config_entry.entry_id)},
            name="SmartEVCC Controller",
            manufacturer="SmartEVCC",
            model="Local EMS",
        )

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        return self.ems.current_state

    @property
    def extra_state_attributes(self) -> dict[str, str | int | float]:
        """Return the state attributes."""
        return {
            "shedded_devices_count": len(self.ems.get_shedded_devices()),
            "last_slow_loop_run": self.ems.get_slow_loop_run() or "None",
            "fuse_limit": self.ems.main_fuse,
        }

    async def async_added_to_hass(self) -> None:
        """Register callbacks when the entity is added to Home Assistant."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_update_{self.ems.config_entry.entry_id}",
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        """Handle updated data from the coordinator/EMS."""
        self.async_write_ha_state()

class SmartEVCCWeatherForecastSensor(SensorEntity):
    """Representation of a SmartEVCC Lowest Temperature Forecast Sensor."""

    def __init__(self, ems: SmartEVCCEMS, description: SensorEntityDescription) -> None:
        """Initialize the sensor."""
        self.ems = ems
        self.entity_description = description
        
        self._attr_unique_id = f"{ems.config_entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, ems.config_entry.entry_id)},
            name="SmartEVCC Controller",
            manufacturer="SmartEVCC",
            model="Local EMS",
        )

    @property
    def native_value(self) -> float | None:
        """Return the lowest expected temperature."""
        return self.ems.lowest_expected_temp

    async def async_added_to_hass(self) -> None:
        """Register callbacks when the entity is added to Home Assistant."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_update_{self.ems.config_entry.entry_id}",
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        """Handle updated data from the coordinator/EMS."""
        self.async_write_ha_state()
