"""The SmartEVCC integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .ems import SmartEVCCEMS

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SmartEVCC from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    ems = SmartEVCCEMS(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = ems

    await ems.async_start()

    # Register update listener to reload config entry when options are updated.
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        ems: SmartEVCCEMS = hass.data[DOMAIN].pop(entry.entry_id)
        await ems.async_stop()

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
