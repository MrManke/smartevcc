"""EMS logic for SmartEVCC."""
import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN,
    CONF_DEBUG_MODE,
    CONF_ENABLE_LOAD_SHEDDING,
    CONF_MAIN_FUSE,
    CONF_P1_PHASE_1,
    CONF_P1_PHASE_2,
    CONF_P1_PHASE_3,
    CONF_SHEDDING_CLIMATES,
    CONF_SHEDDING_LEVEL_1_SWITCHES,
    CONF_SHEDDING_LEVEL_2_SWITCHES,
    CONF_CHARGER_CONTROL_ENTITY,
    CONF_NORDPOOL_ENTITY,
    CONF_EV_BATTERY_LEVEL,
    CONF_EV_TARGET_LEVEL,
    CONF_EV_BATTERY_CAPACITY,
    CONF_EV_MAX_CHARGE_RATE,
    CONF_EV_MIN_SOC,
    CONF_EV_TEMP_SENSOR,
    CONF_EV_COLD_TEMP_THRESHOLD,
    CONF_EV_COLD_CHARGE_RATE,
    CONF_DEPARTURE_TIME,
    CONF_RECOVERY_DURATION,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_ZAPTEC_PHASE_ENTITY,
    DEFAULT_DEBUG_MODE,
    DEFAULT_ENABLE_LOAD_SHEDDING,
    DEFAULT_MAIN_FUSE,
    DEFAULT_EV_TARGET_LEVEL,
    DEFAULT_EV_BATTERY_CAPACITY,
    DEFAULT_EV_MAX_CHARGE_RATE,
    DEFAULT_EV_MIN_SOC,
    DEFAULT_EV_COLD_TEMP_THRESHOLD,
    DEFAULT_EV_COLD_CHARGE_RATE,
    DEFAULT_DEPARTURE_TIME,
    DEFAULT_RECOVERY_DURATION,
)

import math

_LOGGER = logging.getLogger(__name__)

FAST_LOOP_INTERVAL = 10  # seconds
SLOW_LOOP_INTERVAL = 3600  # seconds (1 hour)
OVERLOAD_DURATION_MINOR = 60  # seconds before action on minor overload
OVERLOAD_DURATION_SEVERE = 10  # seconds before action on severe overload
SEVERE_OVERLOAD_MARGIN = 1.5  # Amps above safe_limit
RECOVERY_MARGIN = 1.0  # Amps below safe limit
ZAPTEC_MIN_AMPS = 6.0
CLIMATE_ADJUST_TEMP = 3.0


class SmartEVCCEMS:
    """SmartEVCC Energy Management System."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the EMS."""
        self.hass = hass
        self.config_entry = config_entry
        self._remove_fast_loop = None
        self._remove_slow_loop = None

        # State tracking for filtering
        self._overload_start_time: float | None = None
        self._severe_overload_start_time: float | None = None
        self._safe_start_time: float | None = None
        self._p1_missing_start_time: float | None = None

        # State tracking for load shedding recovery
        self._shedded_devices: list[dict[str, Any]] = []

        # Slow Loop State
        self._price_allows_charging: bool = False
        self._slow_loop_last_run: str = ""
        self.lowest_expected_temp: float | None = None
        self.planned_charging_text: str | None = None

        # Sensor State Machine
        self.current_state: str = "Väntar"

        # Toggled Options from UI Entities (Switch / Number)
        self.force_charge: bool = False
        self.max_price_limit: float = 0.0
        self.low_price_charging_limit: float = 0.0
        self.spike_override: bool = False
        self.phase_balancing: bool = False
        
        # New Dynamic UI Entities (Loaded from Config once on boot, then managed by UI)
        self.main_fuse: float = float(config_entry.options.get(CONF_MAIN_FUSE, config_entry.data.get(CONF_MAIN_FUSE, DEFAULT_MAIN_FUSE)))
        self.enable_load_shedding: bool = bool(config_entry.options.get(CONF_ENABLE_LOAD_SHEDDING, config_entry.data.get(CONF_ENABLE_LOAD_SHEDDING, DEFAULT_ENABLE_LOAD_SHEDDING)))
        self.ev_min_soc: float = float(config_entry.options.get(CONF_EV_MIN_SOC, config_entry.data.get(CONF_EV_MIN_SOC, DEFAULT_EV_MIN_SOC)))
        self.ev_target_level: float = float(config_entry.options.get(CONF_EV_TARGET_LEVEL, config_entry.data.get(CONF_EV_TARGET_LEVEL, DEFAULT_EV_TARGET_LEVEL)))
        self.ev_battery_capacity: float = float(config_entry.options.get(CONF_EV_BATTERY_CAPACITY, config_entry.data.get(CONF_EV_BATTERY_CAPACITY, DEFAULT_EV_BATTERY_CAPACITY)))
        self.ev_max_charge_rate: float = float(config_entry.options.get(CONF_EV_MAX_CHARGE_RATE, config_entry.data.get(CONF_EV_MAX_CHARGE_RATE, DEFAULT_EV_MAX_CHARGE_RATE)))
        self.ev_cold_temp_threshold: float = float(config_entry.options.get(CONF_EV_COLD_TEMP_THRESHOLD, config_entry.data.get(CONF_EV_COLD_TEMP_THRESHOLD, DEFAULT_EV_COLD_TEMP_THRESHOLD)))
        self.ev_cold_charge_rate: float = float(config_entry.options.get(CONF_EV_COLD_CHARGE_RATE, config_entry.data.get(CONF_EV_COLD_CHARGE_RATE, DEFAULT_EV_COLD_CHARGE_RATE)))
        self.recovery_duration: float = float(config_entry.options.get(CONF_RECOVERY_DURATION, config_entry.data.get(CONF_RECOVERY_DURATION, DEFAULT_RECOVERY_DURATION)))
        self.debug_mode: bool = bool(config_entry.options.get(CONF_DEBUG_MODE, config_entry.data.get(CONF_DEBUG_MODE, DEFAULT_DEBUG_MODE)))
        self.charger_status_entity: str | None = config_entry.options.get(CONF_CHARGER_STATUS_ENTITY) or config_entry.data.get(CONF_CHARGER_STATUS_ENTITY)
        self.zaptec_phase_entity: str | None = config_entry.options.get(CONF_ZAPTEC_PHASE_ENTITY) or config_entry.data.get(CONF_ZAPTEC_PHASE_ENTITY)

    def _set_state(self, new_state: str) -> None:
        """Update the component state and notify listeners."""
        if self.current_state != new_state:
            _LOGGER.info("State changed: %s -> %s", self.current_state, new_state)
            self.current_state = new_state
            async_dispatcher_send(
                self.hass, f"{DOMAIN}_update_{self.config_entry.entry_id}"
            )

    def get_shedded_devices(self) -> list[dict[str, Any]]:
        """Return the current list of shedded devices."""
        return self._shedded_devices

    def get_slow_loop_run(self) -> str:
        """Return the last slow loop text."""
        return self._slow_loop_last_run

    @property
    def shedding_level_1_switches(self) -> list[str]:
        """Return the Level 1 list of switch entities for shedding."""
        opt = self.config_entry.options.get(CONF_SHEDDING_LEVEL_1_SWITCHES)
        if opt is not None:
             return opt
        return self.config_entry.data.get(CONF_SHEDDING_LEVEL_1_SWITCHES, [])

    @property
    def shedding_level_2_switches(self) -> list[str]:
        """Return the Level 2 list of switch entities for shedding."""
        opt = self.config_entry.options.get(CONF_SHEDDING_LEVEL_2_SWITCHES)
        if opt is not None:
             return opt
        return self.config_entry.data.get(CONF_SHEDDING_LEVEL_2_SWITCHES, [])

    @property
    def shedding_climates(self) -> list[str]:
        """Return the list of climate entities for shedding."""
        opt = self.config_entry.options.get(CONF_SHEDDING_CLIMATES)
        if opt is not None:
             return opt
        return self.config_entry.data.get(CONF_SHEDDING_CLIMATES, [])

    @property
    def zaptec_charger(self) -> str | None:
        """Return the Zaptec charger entity ID."""
        opt = self.config_entry.options.get(CONF_CHARGER_CONTROL_ENTITY)
        if opt is not None:
            return opt
        return self.config_entry.data.get(CONF_CHARGER_CONTROL_ENTITY)

    async def async_start(self) -> None:
        """Start the EMS loops."""
        _LOGGER.debug("Starting SmartEVCC EMS fast loop")
        self._remove_fast_loop = async_track_time_interval(
            self.hass,
            self._fast_loop_tick,
            timedelta(seconds=FAST_LOOP_INTERVAL),
        )
        
        _LOGGER.debug("Starting SmartEVCC EMS slow loop")
        self._remove_slow_loop = async_track_time_interval(
            self.hass,
            self._slow_loop_tick,
            timedelta(seconds=SLOW_LOOP_INTERVAL),
        )
        # Run slow loop once immediately on startup
        self.hass.async_create_task(self._slow_loop_tick(datetime.now()))

    async def async_stop(self) -> None:
        """Stop the EMS loops."""
        _LOGGER.debug("Stopping SmartEVCC EMS loops")
        if self._remove_fast_loop:
            self._remove_fast_loop()
            self._remove_fast_loop = None
        if self._remove_slow_loop:
            self._remove_slow_loop()
            self._remove_slow_loop = None

    def _get_float_state(self, entity_id: str | None) -> float | None:
        """Helper to get and parse float state safely."""
        if not entity_id:
            return None
        try:
            state: State | None = self.hass.states.get(entity_id)
            if state and state.state not in ("unknown", "unavailable"):
                return float(state.state)
        except (ValueError, TypeError) as err:
            _LOGGER.error("Error reading %s: %s", entity_id, err)
        return None

    def _get_zaptec_amps(self) -> float | None:
        """Get the current Zaptec charger amp limit."""
        entity_id = self.zaptec_charger
        return self._get_float_state(entity_id)

    async def _set_zaptec_amps(self, amps: float) -> None:
        """Set the Zaptec charger amp limit."""
        entity_id = self.zaptec_charger
        if entity_id:
            _LOGGER.info("Setting Zaptec charger %s to %sA", entity_id, amps)
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": entity_id, "value": amps},
                blocking=False,
            )

    async def _shed_next_load(self) -> None:
        """Shed the next available load (Switch then Climate)."""
        # 1. Try Level 1 Switches
        for eid in self.shedding_level_1_switches:
            if any(shed.get("entity_id") == eid for shed in self._shedded_devices):
                continue

            state = self.hass.states.get(eid)
            if state and state.state == "on":
                self._shedded_devices.append(
                    {
                        "entity_id": eid,
                        "type": "switch",
                        "original_state": "on",
                        "timestamp": time.time(),
                    }
                )
                _LOGGER.info("Shedding Level 1 switch %s", eid)
                domain = eid.split(".")[0]
                await self.hass.services.async_call(
                    domain, "turn_off", {"entity_id": eid}, blocking=False
                )
                return

        # 2. Try Level 2 Switches
        for eid in self.shedding_level_2_switches:
            if any(shed.get("entity_id") == eid for shed in self._shedded_devices):
                continue

            state = self.hass.states.get(eid)
            if state and state.state == "on":
                self._shedded_devices.append(
                    {
                        "entity_id": eid,
                        "type": "switch",
                        "original_state": "on",
                        "timestamp": time.time(),
                    }
                )
                _LOGGER.info("Shedding Level 2 switch %s", eid)
                domain = eid.split(".")[0]
                await self.hass.services.async_call(
                    domain, "turn_off", {"entity_id": eid}, blocking=False
                )
                return

        # 3. Try Climates
        for eid in self.shedding_climates:
            if any(shed.get("entity_id") == eid for shed in self._shedded_devices):
                continue

            state = self.hass.states.get(eid)
            if state:
                current_state = state.state
                if current_state in ("heat", "cool"):
                    target_temp = state.attributes.get("temperature")
                    if target_temp is not None:
                        new_temp = (
                            target_temp - CLIMATE_ADJUST_TEMP
                            if current_state == "heat"
                            else target_temp + CLIMATE_ADJUST_TEMP
                        )
                        self._shedded_devices.append(
                            {
                                "entity_id": eid,
                                "type": "climate",
                                "original_state": current_state,
                                "original_temp": target_temp,
                                "timestamp": time.time(),
                            }
                        )
                        _LOGGER.info(
                            "Shedding climate %s (adjusting temp from %s to %s)",
                            eid,
                            target_temp,
                            new_temp,
                        )
                        await self.hass.services.async_call(
                            "climate",
                            "set_temperature",
                            {"entity_id": eid, "temperature": new_temp},
                            blocking=False,
                        )
                        return

        _LOGGER.warning(
            "SmartEVCC: Max limit exceeded, Zaptec is at min, and no more loads to shed! Pausing Zaptec."
        )
        zaptec_entity = self.zaptec_charger
        if zaptec_entity:
            # Attempt to derive the switch name if a number entity was provided, or just use domain 'switch'
            zaptec_switch = zaptec_entity.replace("number.", "switch.").replace("_max_laddstrom", "_laddar")
            if "zaptec" not in zaptec_switch:
                zaptec_switch = "switch.zaptec_go_laddar"
            
            _LOGGER.info("Pausing Zaptec charger via %s", zaptec_switch)
            await self.hass.services.async_call(
                "switch", "turn_off", {"entity_id": zaptec_switch}, blocking=False
            )

    async def _restore_previous_load(self, headroom: float = 1.0) -> None:
        """Restore previously shed loads or increase Zaptec mathematically."""
        if self._shedded_devices:
            # Restore the last shedded device (LIFO)
            device = self._shedded_devices.pop()
            eid = device["entity_id"]
            dtype = device["type"]

            _LOGGER.info("Restoring shed load %s", eid)
            if dtype == "switch":
                if device["original_state"] == "on":
                    domain = eid.split(".")[0]
                    await self.hass.services.async_call(
                        domain, "turn_on", {"entity_id": eid}, blocking=False
                    )
            elif dtype == "climate":
                temp = device.get("original_temp")
                if temp is not None:
                    await self.hass.services.async_call(
                        "climate",
                        "set_temperature",
                        {"entity_id": eid, "temperature": temp},
                        blocking=False,
                    )
            return

        # If no loads to restore, try to increase Zaptec via EVCC math
        zaptec_amps = self._get_zaptec_amps()
        if zaptec_amps is not None and zaptec_amps < self.main_fuse:
            # EVCC style jump: Add exact headroom, capped by max fuse and configured max charge rate
            upper_limit = min(float(self.main_fuse), float(self.ev_max_charge_rate))
            new_amps = min(upper_limit, float(zaptec_amps + headroom))
            new_amps = float(round(new_amps, 1))  # Clean 1 decimal rounding

            if new_amps > zaptec_amps:
                _LOGGER.debug(
                    "Recovery: Increasing Zaptec from %sA to %sA (Headroom: +%.1fA)",
                    zaptec_amps,
                    new_amps,
                    headroom,
                )
                await self._set_zaptec_amps(new_amps)

    async def _trigger_overload_action(self, max_current: float) -> None:
        """Action taken when prolonged overload is detected."""
        zaptec_amps = self._get_zaptec_amps()

        # 1. First line of defense: Zaptec Cloud Regulation
        if zaptec_amps is not None and zaptec_amps > ZAPTEC_MIN_AMPS:
            new_amps = max(ZAPTEC_MIN_AMPS, zaptec_amps - 1.0)
            _LOGGER.warning(
                "Overload detected (%.2fA). Reducing Zaptec from %sA to %sA",
                max_current,
                zaptec_amps,
                new_amps,
            )
            await self._set_zaptec_amps(new_amps)
            return

        # 2. Second line of defense: Toggleable Load Shedding
        if self.enable_load_shedding:
            _LOGGER.warning(
                "Overload persisted at Zaptec min. Shedding next available load."
            )
            await self._shed_next_load()
        else:
            _LOGGER.warning(
                "Overload persisted but Load Shedding is disabled. Cannot reduce further."
            )

    async def _slow_loop_tick(self, now: datetime) -> None:
        """Execute the slow loop logic (Price & Capacity Planner)."""
        _LOGGER.debug("Running SmartEVCC slow loop price planner")
        
        cfg = self.config_entry
        nordpool_id = cfg.options.get(CONF_NORDPOOL_ENTITY) or cfg.data.get(CONF_NORDPOOL_ENTITY)
        soc_id = cfg.options.get(CONF_EV_BATTERY_LEVEL) or cfg.data.get(CONF_EV_BATTERY_LEVEL)
        temp_id = cfg.options.get(CONF_EV_TEMP_SENSOR) or cfg.data.get(CONF_EV_TEMP_SENSOR)
        
        min_soc = self.ev_min_soc
        target_soc = self.ev_target_level
        capacity = self.ev_battery_capacity
        max_rate = self.ev_max_charge_rate
        cold_threshold = self.ev_cold_temp_threshold
        cold_rate = self.ev_cold_charge_rate
        departure_time_str = cfg.options.get(CONF_DEPARTURE_TIME, cfg.data.get(CONF_DEPARTURE_TIME, DEFAULT_DEPARTURE_TIME))

        if not nordpool_id or not soc_id:
            _LOGGER.warning("Slow Loop missing Nordpool or EV SOC entity. Allowing charging by default.")
            self._price_allows_charging = True
            return

        current_soc = self._get_float_state(soc_id)
        if current_soc is None:
            _LOGGER.warning("Could not read EV SOC. Allowing charging by default.")
            self._price_allows_charging = True
            return

        # 1. Check Minimum SoC (Emergency Charging)
        if current_soc < min_soc:
            self._price_allows_charging = True
            self._slow_loop_last_run = f"Emergency Charging: Current SoC ({current_soc:.1f}%) < Min SoC ({min_soc:.1f}%)"
            _LOGGER.info(self._slow_loop_last_run)
            return

        # 2. Calculate Energy Needed
        energy_needed_kwh = (target_soc - current_soc) / 100.0 * capacity
        if energy_needed_kwh <= 0:
            _LOGGER.info("EV Target SOC reached (%.1f%% >= %.1f%%). Pausing charging.", current_soc, target_soc)
            self._price_allows_charging = False
            return

        # 3. Climate Throttle Logic
        assumed_rate = max_rate
        if temp_id:
            min_expected_temp = None

            if temp_id.startswith("weather."):
                try:
                    response = await self.hass.services.async_call(
                        "weather",
                        "get_forecasts",
                        {"entity_id": temp_id, "type": "hourly"},
                        blocking=True,
                        return_response=True,
                    )
                    if isinstance(response, dict):
                        forecasts = response.get(temp_id, {}).get("forecast", [])
                        if forecasts:
                            # Look at the next 24 hours (or less if fewer are available)
                            temps = [f.get("temperature") for f in forecasts[:24] if f.get("temperature") is not None]
                            if temps:
                                min_expected_temp = min(temps)
                                _LOGGER.debug("Weather forecast next 24h min temp: %.1f", min_expected_temp)
                except Exception as e:
                    _LOGGER.error("Failed to fetch weather forecast for %s: %s", temp_id, e)
            
            # Fallback for standard sensors or if forecast fails
            if min_expected_temp is None:
                min_expected_temp = self._get_float_state(temp_id)
                
            self.lowest_expected_temp = min_expected_temp

            if min_expected_temp is not None and min_expected_temp < cold_threshold:
                _LOGGER.info("Cold weather expected (%.1f°C < %.1f°C). Throttling assumed charge rate to %.1fkW", min_expected_temp, cold_threshold, cold_rate)
                assumed_rate = cold_rate

        hours_needed = math.ceil(energy_needed_kwh / assumed_rate)
        _LOGGER.debug("Need %.1fkWh at assumed rate %.1fkW -> %d hours requested.", energy_needed_kwh, assumed_rate, hours_needed)

        # 4. Price Optimization
        nordpool_state = self.hass.states.get(nordpool_id)
        if not nordpool_state or "today" not in nordpool_state.attributes:
            _LOGGER.error("Nordpool state or attributes missing! Allowing charging by default.")
            self._price_allows_charging = True
            return

        today_prices = nordpool_state.attributes.get("today", [])
        tomorrow_prices = nordpool_state.attributes.get("tomorrow", []) or []

        # Parse departure time
        try:
            dep_hour, dep_minute = map(int, departure_time_str.split(":"))
        except ValueError:
            dep_hour, dep_minute = 7, 0
            _LOGGER.error("Invalid departure time format '%s', defaulting to 07:00", departure_time_str)

        all_future_prices = []
        current_hour = now.hour
        
        # Add remaining hours today
        for i in range(current_hour, len(today_prices)):
            all_future_prices.append({"hour": i, "price": today_prices[i], "day": "today"})
            
        # Add hours tomorrow up until departure
        for i in range(min(len(tomorrow_prices), dep_hour + 1)): # Include departure hour
            all_future_prices.append({"hour": i, "price": tomorrow_prices[i], "day": "tomorrow"})

        if not all_future_prices:
            self._price_allows_charging = True
            self.planned_charging_text = "Ingen laddning planerad (Priser saknas)"
            return

        # SPIKE OVERRIDE CHECK
        if self.spike_override and today_prices and tomorrow_prices:
            today_avg = sum(today_prices) / len(today_prices)
            tomorrow_max = max(tomorrow_prices)
            spike_threshold = 1.50  # SEK difference threshold
            
            if (tomorrow_max - today_avg) >= spike_threshold:
                _LOGGER.info("PRICE SPIKE DETECTED! Tomorrow max (%.2f) is %.2f higher than today avg (%.2f). Forcing 100%% Target.", tomorrow_max, (tomorrow_max - today_avg), today_avg)
                energy_needed_kwh = (100.0 - current_soc) / 100.0 * capacity
                if energy_needed_kwh > 0:
                     hours_needed = math.ceil(energy_needed_kwh / assumed_rate)
                     _LOGGER.debug("Recalculated Spike hours needed: %d", hours_needed)

        # Sort based on price to find cheapest N hours
        sorted_prices = sorted(all_future_prices, key=lambda x: x["price"])
        cheapest_hours = sorted_prices[:hours_needed]

        # BUILD PLANNED CHARGING SENSOR TEXT
        if not cheapest_hours:
            self.planned_charging_text = "Målet nått. Ingen laddning."
        else:
            planned_sorted = sorted(cheapest_hours, key=lambda x: (x["day"], x["hour"]))
            avg_price = sum(h["price"] for h in cheapest_hours) / len(cheapest_hours)
            
            blocks = []
            for h in planned_sorted:
                day_prefix = "Idag" if h["day"] == "today" else "Imorgon"
                blocks.append(f"{day_prefix} {h['hour']:02d}:00")
                
            if len(blocks) > 3:
                blocks_text = f"{blocks[0]} ... {blocks[-1]}"
            else:
                blocks_text = ", ".join(blocks)
                
            self.planned_charging_text = f"{blocks_text} (Snitt: {avg_price:.2f} kr)"

        # PRIORITY 1: Low Price Limit
        # Check if the current hour's price is below the low_price_charging_limit
        current_price = today_prices[current_hour] if current_hour < len(today_prices) else 0.0
        if current_price < self.low_price_charging_limit:
            self._price_allows_charging = True
            self._slow_loop_last_run = f"Charging allowed: Price ({current_price:.2f}) < Low Limit ({self.low_price_charging_limit:.2f})"
            _LOGGER.info(self._slow_loop_last_run)
            return

        # PRIORITY 2: Force Charge
        if self.force_charge:
            self._price_allows_charging = True
            self._slow_loop_last_run = "Charging allowed: Force Charge is ON"
            _LOGGER.info(self._slow_loop_last_run)
            return

        # PRIORITY 3: Max Price Limit
        if current_price > self.max_price_limit and self.max_price_limit > 0:
            self._price_allows_charging = False
            self._slow_loop_last_run = f"Charging blocked: Price ({current_price:.2f}) > Max Limit ({self.max_price_limit:.2f})"
            _LOGGER.info(self._slow_loop_last_run)
            return

        # PRIORITY 4: Normal Schedule
        charge_now = any(h["hour"] == current_hour and h["day"] == "today" for h in cheapest_hours)
        
        self._price_allows_charging = charge_now
        self._slow_loop_last_run = f"Needed {hours_needed}h. Charge now: {charge_now}."
        _LOGGER.info(self._slow_loop_last_run)

    async def _fast_loop_tick(self, now: datetime) -> None:
        """Execute the fast loop logic (Fuse Protection)."""
        data = self.config_entry.data

        l1_id = data.get(CONF_P1_PHASE_1)
        l2_id = data.get(CONF_P1_PHASE_2)
        l3_id = data.get(CONF_P1_PHASE_3)

        l1_amps = self._get_float_state(l1_id)
        if l1_amps is not None and l1_amps > 100:
            l1_amps = l1_amps / 230.0

        l2_amps = self._get_float_state(l2_id)
        if l2_amps is not None and l2_amps > 100:
            l2_amps = l2_amps / 230.0

        l3_amps = self._get_float_state(l3_id)
        if l3_amps is not None and l3_amps > 100:
            l3_amps = l3_amps / 230.0

        fuse_limit = self.main_fuse
        safe_limit = fuse_limit - 0.5  # e.g. 15.5A for 16A fuse
        severe_limit = fuse_limit + SEVERE_OVERLOAD_MARGIN  # e.g. 17.5A

        loads = {"L1": l1_amps, "L2": l2_amps, "L3": l3_amps}
        
        now_ts = time.time()

        decision = "OK"

        # PHASE 1: EV Status Check (Short-circuit if not connected)
        if self.charger_status_entity:
            status_state = self.hass.states.get(self.charger_status_entity)
            if status_state and status_state.state.lower() == "disconnected":
                decision = "Disconnected - Charger OFF"
                self._set_state("Ej ansluten")
                
                # Turn off the charger completely instead of forcing 6A
                zaptec_entity = self.zaptec_charger
                if zaptec_entity:
                    zaptec_switch = zaptec_entity.replace("number.", "switch.").replace("_max_laddstrom", "_laddar")
                    if "zaptec" not in zaptec_switch:
                        zaptec_switch = "switch.zaptec_go_laddar"
                        
                    switch_state = self.hass.states.get(zaptec_switch)
                    if switch_state and switch_state.state != "off":
                        _LOGGER.info("EV Disconnected: Shutting down charger completely via %s", zaptec_switch)
                        await self.hass.services.async_call(
                            "switch", "turn_off", {"entity_id": zaptec_switch}, blocking=False
                        )
                
                # Reset timers so recovery doesn't trigger unexpectedly later
                self._safe_start_time = None
                self._overload_start_time = None
                self._severe_overload_start_time = None
                
                if self.debug_mode:
                    await self.hass.async_add_executor_job(
                        self._dump_debug_data, loads, safe_limit, decision
                    )
                return

        # PHASE 4 INTEGRATION: If price/schedule planner blocks charging, override.
        if not self._price_allows_charging:
            _LOGGER.debug("Price Optimizer: Charging blocked. Pausing Zaptec/forcing to min.")
            decision = "Price Planner: Paused"
            self._set_state("Price_Wait")
            
            zaptec_entity = self.zaptec_charger
            if zaptec_entity:
                # Attempt to derive the switch name if a number entity was provided, or just use domain 'switch'
                zaptec_switch = zaptec_entity.replace("number.", "switch.").replace("_max_laddstrom", "_laddar")
                if "zaptec" not in zaptec_switch:
                    zaptec_switch = "switch.zaptec_go_laddar"
                
                state = self.hass.states.get(zaptec_switch)
                if not state or state.state != "off":
                    _LOGGER.info("Pausing Zaptec charger via %s", zaptec_switch)
                    await self.hass.services.async_call(
                        "switch", "turn_off", {"entity_id": zaptec_switch}, blocking=False
                    )
            
            # If we're forcing 6A/paused, don't execute the rest of the limit recovery loop
            # BUT we still need to process P1 missing logic first.
            if None in loads.values():
                 pass # Let the P1 logic below handle it natively
            else:
                 if self.debug_mode:
                    await self.hass.async_add_executor_job(
                        self._dump_debug_data, loads, safe_limit, decision
                    )
                 return

        if None in loads.values():
            p1_start = self._p1_missing_start_time
            if p1_start is None:
                self._p1_missing_start_time = now_ts
            elif now_ts - p1_start >= 30:
                _LOGGER.error("P1 meter data missing for >30s! Forcing Zaptec to minimum.")
                decision = "P1 Data Missing (Fallback to 6A)"
                self._set_state("Fuse_Protect_Paused")
                
                zaptec_amps = self._get_zaptec_amps()
                if zaptec_amps is None or zaptec_amps > ZAPTEC_MIN_AMPS:
                    await self._set_zaptec_amps(ZAPTEC_MIN_AMPS)
            
            if self.debug_mode:
                await self.hass.async_add_executor_job(
                    self._dump_debug_data, loads, safe_limit, decision
                )
            return

        self._p1_missing_start_time = None
        valid_loads = [v for v in loads.values() if v is not None]
        max_current = max(valid_loads) if valid_loads else None

        if max_current is not None:
            # PHASE BALANCING CHECK (Intercept Overload)
            if self.phase_balancing and self.zaptec_phase_entity:
                l1 = loads.get("L1")
                if l1 is None:
                    l1 = 0.0
                    
                if max_current > safe_limit and l1 <= safe_limit - 2.0:
                    state = self.hass.states.get(self.zaptec_phase_entity)
                    if state and str(state.state) != "1":
                        _LOGGER.warning("Phase Imbalance (L1 safe, L2/L3 high). Downgrading Zaptec to 1-phase mode.")
                        await self.hass.services.async_call("select", "select_option", {"entity_id": self.zaptec_phase_entity, "option": "1"}, blocking=False)
                        decision = "Phase Balancing Triggered -> 1-phase mode"
                        if self.debug_mode:
                            await self.hass.async_add_executor_job(
                                self._dump_debug_data, loads, safe_limit, decision
                            )
                        return

            if max_current > severe_limit:
                # Severe overload
                decision = f"Severe Overload ({max_current}A)"
                sev_start = self._severe_overload_start_time
                if sev_start is None:
                    self._severe_overload_start_time = now_ts
                    sev_start = now_ts
                self._safe_start_time = None

                if (
                    now_ts - sev_start
                    >= OVERLOAD_DURATION_SEVERE
                ):
                    decision += " -> ACTION TAKEN"
                    await self._trigger_overload_action(max_current)
                    self._severe_overload_start_time = now_ts  # Reset
                    self._overload_start_time = None  # Reset minor

            elif max_current > safe_limit:
                # Minor overload
                decision = f"Minor Overload ({max_current}A)"
                self._severe_overload_start_time = None
                ov_start = self._overload_start_time
                if ov_start is None:
                    self._overload_start_time = now_ts
                    ov_start = now_ts
                self._safe_start_time = None

                if now_ts - ov_start >= OVERLOAD_DURATION_MINOR:
                    decision += " -> ACTION TAKEN"
                    await self._trigger_overload_action(max_current)
                    self._overload_start_time = now_ts  # Reset

            else:
                # Below safe limit
                self._severe_overload_start_time = None
                self._overload_start_time = None

                headroom = safe_limit - max_current
                if headroom >= 1.0:
                    decision = f"Recovery Range (+{headroom:.1f}A available)"
                    safe_start = self._safe_start_time
                    if safe_start is None:
                        self._safe_start_time = now_ts
                        safe_start = now_ts

                    if now_ts - safe_start >= self.recovery_duration:
                        decision += " -> ACTION TAKEN"
                        
                        zaptec_turned_on = False
                        zaptec_entity = self.zaptec_charger
                        if zaptec_entity:
                            zaptec_switch = zaptec_entity.replace("number.", "switch.").replace("_max_laddstrom", "_laddar")
                            if "zaptec" not in zaptec_switch:
                                zaptec_switch = "switch.zaptec_go_laddar"
                            
                            state = self.hass.states.get(zaptec_switch)
                            if state and state.state == "off":
                                zaptec_turned_on = True
                                _LOGGER.info("Recovery: Resuming Zaptec charger via %s", zaptec_switch)
                                await self.hass.services.async_call(
                                    "switch", "turn_on", {"entity_id": zaptec_switch}, blocking=False
                                )
                        
                        if not zaptec_turned_on:
                            # PHASE BALANCING RESTORE
                            phase_restored = False
                            if self.phase_balancing and self.zaptec_phase_entity and headroom >= 6.0:
                                state = self.hass.states.get(self.zaptec_phase_entity)
                                if state and str(state.state) == "1":
                                    _LOGGER.info("Headroom restored! Upgrading Zaptec back to 3-phase mode.")
                                    await self.hass.services.async_call("select", "select_option", {"entity_id": self.zaptec_phase_entity, "option": "3"}, blocking=False)
                                    phase_restored = True
                                    
                            if not phase_restored:
                                await self._restore_previous_load(headroom)
                            
                        self._safe_start_time = now_ts  # Reset
                else:
                    # In hysteresis deadband (safe_limit - 1.0 <= max_current <= safe_limit)
                    decision = f"Deadband ({max_current}A)"
        if self._price_allows_charging:
            # We are currently allowed to charge, update State Machine based on Fast Loop activity
            if self._shedded_devices:
                self._set_state("Lastbalanserar")
            else:
                zaptec_amps = self._get_zaptec_amps()
                if max_current is not None and max_current > safe_limit:
                    self._set_state("Överbelastning")
                elif zaptec_amps is not None and zaptec_amps > ZAPTEC_MIN_AMPS:
                    self._set_state("Laddar")
                else:
                    self._set_state("Väntar")

        if self.debug_mode:
            _LOGGER.debug("SmartEVCC Fast Loop - Phase Loads: %s | Limit: %sA | Decision: %s", loads, safe_limit, decision)
            # Run the file I/O safely in an executor to not block the async loop
            await self.hass.async_add_executor_job(
                self._dump_debug_data, loads, safe_limit, decision
            )

    def _dump_debug_data(
        self, loads: dict[str, float | None], safe_limit: float, decision: str
    ) -> None:
        """Dump debug data to JSON file."""
        export_dir = self.hass.config.path("custom_components", DOMAIN, "debug_logs")
        os.makedirs(export_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(export_dir, f"smartevcc_debug_{timestamp}.json")

        debug_data = {
            "timestamp": datetime.now().isoformat(),
            "main_fuse": self.main_fuse,
            "safe_limit": safe_limit,
            "phase_loads": loads,
            "decision": decision,
            "price_allows_charging": self._price_allows_charging,
            "slow_loop_last_run": self._slow_loop_last_run,
            "shedded_devices_count": len(self._shedded_devices),
            "shedded_devices": self._shedded_devices,
        }

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(debug_data, f, indent=2)
        except OSError as err:
            _LOGGER.error("Failed to write debug file: %s", err)
