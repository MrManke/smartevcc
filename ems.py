"""EMS logic for SmartEVCC."""
import asyncio
import json
import logging
import os
import time
from datetime import datetime
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
    CONF_EV_TEMP_SENSOR,
    CONF_EV_COLD_TEMP_THRESHOLD,
    CONF_EV_COLD_CHARGE_RATE,
    CONF_DEPARTURE_TIME,
    DEFAULT_DEBUG_MODE,
    DEFAULT_ENABLE_LOAD_SHEDDING,
    DEFAULT_MAIN_FUSE,
    DEFAULT_EV_TARGET_LEVEL,
    DEFAULT_EV_BATTERY_CAPACITY,
    DEFAULT_EV_MAX_CHARGE_RATE,
    DEFAULT_EV_COLD_TEMP_THRESHOLD,
    DEFAULT_EV_COLD_CHARGE_RATE,
    DEFAULT_DEPARTURE_TIME,
)

import math

_LOGGER = logging.getLogger(__name__)

FAST_LOOP_INTERVAL = 10  # seconds
SLOW_LOOP_INTERVAL = 3600  # seconds (1 hour)
OVERLOAD_DURATION_MINOR = 60  # seconds before action on minor overload
OVERLOAD_DURATION_SEVERE = 10  # seconds before action on severe overload
SEVERE_OVERLOAD_MARGIN = 1.5  # Amps above safe_limit
RECOVERY_DURATION = 180  # 3 minutes continuous below safe limit
RECOVERY_MARGIN = 1.5  # Amps below safe limit
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

        # Sensor State Machine
        self.current_state: str = "Idle"

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
    def debug_mode(self) -> bool:
        """Return if debug mode is enabled."""
        return self.config_entry.options.get(CONF_DEBUG_MODE, DEFAULT_DEBUG_MODE)

    @property
    def enable_load_shedding(self) -> bool:
        """Return if load shedding is enabled."""
        return self.config_entry.options.get(
            CONF_ENABLE_LOAD_SHEDDING, DEFAULT_ENABLE_LOAD_SHEDDING
        )

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
    def main_fuse(self) -> float:
        """Return the configured main fuse limit."""
        return float(self.config_entry.data.get(CONF_MAIN_FUSE, DEFAULT_MAIN_FUSE))

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
            asyncio.timedelta(seconds=FAST_LOOP_INTERVAL),
        )
        
        _LOGGER.debug("Starting SmartEVCC EMS slow loop")
        self._remove_slow_loop = async_track_time_interval(
            self.hass,
            self._slow_loop_tick,
            asyncio.timedelta(seconds=SLOW_LOOP_INTERVAL),
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
        if self.zaptec_charger:
            # Attempt to derive the switch name if a number entity was provided, or just use domain 'switch'
            zaptec_switch = self.zaptec_charger.replace("number.", "switch.").replace("_max_laddstrom", "_laddar")
            if "zaptec" not in zaptec_switch:
                zaptec_switch = "switch.zaptec_go_laddar"
            
            _LOGGER.info("Pausing Zaptec charger via %s", zaptec_switch)
            await self.hass.services.async_call(
                "switch", "turn_off", {"entity_id": zaptec_switch}, blocking=False
            )

    async def _restore_previous_load(self) -> None:
        """Restore previously shed loads or increase Zaptec."""
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

        # If no loads to restore, try to increase Zaptec
        zaptec_amps = self._get_zaptec_amps()
        if zaptec_amps is not None and zaptec_amps < self.main_fuse:
            # Increase by 1A, up to the fuse limit
            new_amps = min(self.main_fuse, zaptec_amps + 1.0)
            _LOGGER.debug(
                "Recovery: Increasing Zaptec charging from %sA to %sA",
                zaptec_amps,
                new_amps,
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
        
        target_soc = float(cfg.options.get(CONF_EV_TARGET_LEVEL, cfg.data.get(CONF_EV_TARGET_LEVEL, DEFAULT_EV_TARGET_LEVEL)))
        capacity = float(cfg.options.get(CONF_EV_BATTERY_CAPACITY, cfg.data.get(CONF_EV_BATTERY_CAPACITY, DEFAULT_EV_BATTERY_CAPACITY)))
        max_rate = float(cfg.options.get(CONF_EV_MAX_CHARGE_RATE, cfg.data.get(CONF_EV_MAX_CHARGE_RATE, DEFAULT_EV_MAX_CHARGE_RATE)))
        cold_threshold = float(cfg.options.get(CONF_EV_COLD_TEMP_THRESHOLD, cfg.data.get(CONF_EV_COLD_TEMP_THRESHOLD, DEFAULT_EV_COLD_TEMP_THRESHOLD)))
        cold_rate = float(cfg.options.get(CONF_EV_COLD_CHARGE_RATE, cfg.data.get(CONF_EV_COLD_CHARGE_RATE, DEFAULT_EV_COLD_CHARGE_RATE)))
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

        # 1. Calculate Energy Needed
        energy_needed_kwh = (target_soc - current_soc) / 100.0 * capacity
        if energy_needed_kwh <= 0:
            _LOGGER.info("EV Target SOC reached (%.1f%% >= %.1f%%). Pausing charging.", current_soc, target_soc)
            self._price_allows_charging = False
            return

        # 2. Climate Throttle Logic
        assumed_rate = max_rate
        if temp_id:
            current_temp = self._get_float_state(temp_id)
            if current_temp is not None and current_temp < cold_threshold:
                _LOGGER.info("Cold weather detected (%.1f°C < %.1f°C). Throttling assumed charge rate to %.1fkW", current_temp, cold_threshold, cold_rate)
                assumed_rate = cold_rate

        hours_needed = math.ceil(energy_needed_kwh / assumed_rate)
        _LOGGER.debug("Need %.1fkWh at assumed rate %.1fkW -> %d hours requested.", energy_needed_kwh, assumed_rate, hours_needed)

        # 3. Price Optimization
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
            return

        # Sort based on price to find cheapest N hours
        sorted_prices = sorted(all_future_prices, key=lambda x: x["price"])
        cheapest_hours = sorted_prices[:hours_needed]

        # Is the CURRENT hour in the cheapest list?
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
        l2_amps = self._get_float_state(l2_id)
        l3_amps = self._get_float_state(l3_id)

        fuse_limit = self.main_fuse
        safe_limit = fuse_limit - 0.5  # e.g. 15.5A for 16A fuse
        severe_limit = fuse_limit + SEVERE_OVERLOAD_MARGIN  # e.g. 17.5A

        loads = {"L1": l1_amps, "L2": l2_amps, "L3": l3_amps}
        
        now_ts = time.time()

        # Determine what state we ALREADY are in right now visually
        decision = "OK"

        # PHASE 4 INTEGRATION: If price/schedule planner blocks charging, override.
        if not self._price_allows_charging:
            _LOGGER.debug("Price Optimizer: Charging blocked. Pausing Zaptec/forcing to min.")
            decision = "Price Planner: Paused"
            self._set_state("Price_Wait")
            
            zaptec_amps = self._get_zaptec_amps()
            if zaptec_amps is None or zaptec_amps > ZAPTEC_MIN_AMPS:
                await self._set_zaptec_amps(ZAPTEC_MIN_AMPS)
            
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

                if max_current < (safe_limit - RECOVERY_MARGIN):
                    decision = f"Recovery Range ({max_current}A)"
                    safe_start = self._safe_start_time
                    if safe_start is None:
                        self._safe_start_time = now_ts
                        safe_start = now_ts

                    if now_ts - safe_start >= RECOVERY_DURATION:
                        decision += " -> ACTION TAKEN"
                        await self._restore_previous_load()
                        self._safe_start_time = now_ts  # Reset
                else:
                    # In hysteresis deadband (safe_limit - 1.5 <= max_current <= safe_limit)
                    decision = f"Deadband ({max_current}A)"
        if self._price_allows_charging:
            # We are currently allowed to charge, update State Machine based on Fast Loop activity
            if self._shedded_devices:
                self._set_state("Shedding")
            else:
                zaptec_amps = self._get_zaptec_amps()
                if max_current is not None and max_current > safe_limit:
                    self._set_state("Fuse_Protect_Paused")
                elif zaptec_amps is not None and zaptec_amps > ZAPTEC_MIN_AMPS:
                    self._set_state("Charging")
                else:
                    self._set_state("Idle")

        if self.debug_mode:
            # Run the file I/O safely in an executor to not block the async loop
            await self.hass.async_add_executor_job(
                self._dump_debug_data, loads, safe_limit, decision
            )

    def _dump_debug_data(
        self, loads: dict[str, float | None], safe_limit: float, decision: str
    ) -> None:
        """Dump debug data to JSON file."""
        export_dir = self.hass.config.path("export")
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
