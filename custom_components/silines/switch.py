"""Support for Silines switches with high-performance reactive state rendering."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.exceptions import HomeAssistantError
from .models import StandardRelay
from dataclasses import replace
from . import SilinesConfigEntry, SilinesCoordinator
from .entity import SilinesBaseEntity

async def async_setup_entry(
    hass: HomeAssistant,
    entry: SilinesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Silines switches dynamically from coordinator universal data maps."""
    coordinator = entry.runtime_data
    if not coordinator or not coordinator.data:
        return

    device_state = coordinator.data
    entities: list[SwitchEntity] = []

    if device_state.relay_map:
        entities.extend(
            [
                SilinesSwitch(coordinator, relay_id)
                for relay_id in device_state.relay_map.keys()
            ]
        )

    if hasattr(device_state, "srs_htr_map") and device_state.srs_htr_map:
        entities.extend(
            [
                SilinesSrsHeaterSwitch(coordinator, node_id)
                for node_id in device_state.srs_htr_map.keys()
            ]
        )

    if entities:
        async_add_entities(entities)

class SilinesSwitch(SilinesBaseEntity, SwitchEntity):
    """Switch entity representing a controllable hardware relay channel with state locking."""

    LOCK_PREFIX = "RELAY_"

    def __init__(
        self,
        coordinator: SilinesCoordinator,
        relay_id: int,
    ) -> None:
        """Initialize the switch entity mapping directly to core hardware channels."""
        super().__init__(coordinator)
        self.relay_id = relay_id
        self._attr_unique_id = f"{self.device_prefix}_relay_{relay_id}"
        self._attr_has_entity_name = True
        self.coordinator.relay_switches[self.relay_id] = self
        record = self.__get_coordinator_record()
        self.calculated_state = False if record is None else record.is_on;

    @property
    def name(self) -> str:
        """Return the dynamic name of the relay channel resolved from the state map."""
        record = self.__get_coordinator_record()
        return f"Relay {self.relay_id}" if record is None else record.name

    @property
    def is_on(self) -> bool:
        """Evaluate state properties pulling directly from coordinated data or local lock."""
        return self.calculated_state

    @property
    def available(self) -> bool:
        """Evaluate network accessibility state alongside hardware availability flags."""
        record = self.__get_coordinator_record()
        return super().available and not (record is None) and record.available

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle background telemetry fetch using the strict update_end coordinator-level filter."""
        current_lock = self.coordinator.switch_lock.get(self.__lock_get_key())
        if (current_lock is None) or ((current_lock[0] != 0) and (current_lock[1] == 0)):
            self.calculated_state = self.coordinator.data.relay_map.get(self.relay_id).is_on
        if not current_lock is None: current_lock[0] = 0
        super()._handle_coordinator_update()

         
    """STATIC METHODS -->"""
    def __lock_get_key(self) -> str:
        return f"{self.LOCK_PREFIX}{self.relay_id}"
    
    def __lock_set(self) -> None:
        lock_key     = self.__lock_get_key()
        current_lock = self.coordinator.switch_lock.get(lock_key)
        if current_lock is None : self.coordinator.switch_lock[lock_key] = [0, 1]
        else:
            current_lock[0] = 0
            current_lock[1] += 1

    def __lock_reset(self) -> None:
        lock_key     = self.__lock_get_key()
        current_lock = self.coordinator.switch_lock.get(lock_key)
        if current_lock is None : self.coordinator.switch_lock[lock_key] = [0, 0]
        else:
            current_lock[0] = 0
            if current_lock[1] != 0: current_lock[1] -= 1

    def __get_coordinator_record(self) -> StandardRelay | None :
        return None if self.coordinator.data is None else self.coordinator.data.relay_map.get(self.relay_id)

    async def __send_command(self, url:str, key:str, value:str, description: str | None) -> bool :
        response_text = await self.coordinator.http_client.send_post(url, {key: value}, description)
        if (response_text is None) or not (f"{key}={value}" in response_text):
            raise HomeAssistantError("Invalid response or from Silines controller")

    """STATIC METHODS <--"""

    async def set_relay_state(self, state: bool) -> None:
        """Turn the hardware relay ON/OFF using the double-lock protocol."""

        self.__lock_set()
        state_mem = self.calculated_state

        self.calculated_state = state
        self.async_write_ha_state()

        check_dev = False
        try:
            await self.__send_command("/api/relctrl.cgi", f"k{self.relay_id}", "1" if state else "0", f"set_relay_state({state})")
        except Exception as err:
            self.calculated_state = state_mem
            check_dev = True
            if isinstance(err, HomeAssistantError) : raise
            raise HomeAssistantError(f"Failed to send command to Silines controller: {err}") from err
        finally:
            self.__lock_reset()
            self.coordinator.async_update_listeners()
            if check_dev: self.coordinator.set_sheduled_refresh(0.2, "set_relay_state - check device on command error")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.set_relay_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.set_relay_state(False)

    async def async_pulse(self, duration_ms: int) -> None:
        """Execute short timed pulse cgi payload sequence using coordinator-level matrix locking."""

        if not isinstance(duration_ms, int) or duration_ms is None: return
            
        verification_delay = float(duration_ms) / 1000.0 + 0.2
        mem_state = self.calculated_state

        self.__lock_set()
        self.calculated_state = True
        self.async_write_ha_state()

        check_dev = False
        try:
            await self.__send_command("/api/relctrl.cgi", f"k{self.relay_id}", f"p{duration_ms}", f"async_pulse({self.relay_id},{duration_ms})")
            self.coordinator.set_sheduled_refresh(verification_delay, f"async_pulse() relay_id={self.relay_id}")
        except Exception as err:
            self.calculated_state = mem_state
            check_dev = True
            if isinstance(err, HomeAssistantError) : raise
            raise HomeAssistantError(f"Exception pulse_relay() {self.relay_id}: {err}") from err
        finally:
            self.__lock_reset()
            self.coordinator.async_update_listeners()
            if check_dev: self.coordinator.set_sheduled_refresh(0.2, "relay_pulse - check device on command error")

class SilinesSrsHeaterSwitch(SilinesBaseEntity, SwitchEntity):
    """Switch entity representing controllable built-in heater with state locking."""

    LOCK_PREFIX = "SRS_HEATER_"

    def __init__(self,coordinator: SilinesCoordinator,node_id: str,) -> None:
        """Initialize the SRS heater switch entity using climate node identifiers."""
        super().__init__(coordinator)
        self.node_id = node_id.upper()
        self._attr_unique_id = f"{self.device_prefix}_srs_heater_{self.node_id.lower()}"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:radiator"
        self._attr_translation_key = "srs_heater"
        record = self.__get_coordinator_record()
        self.calculated_state = False if record is None else record;

    @property
    def name(self) -> str:
        """Return the dynamic suffix of the heater entity."""
        return f"Heater {self.node_id}"

    @property
    def is_on(self) -> bool:
        """Evaluate state properties pulling raw status variables straight from coordinated memory."""
        return self.calculated_state

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle background telemetry fetch using the strict update_end coordinator-level filter."""
        current_lock = self.coordinator.switch_lock.get(self.__lock_get_key())
        if (current_lock is None) or ((current_lock[0] != 0) and (current_lock[1] == 0)):
            self.calculated_state = self.coordinator.data.srs_htr_map.get(self.node_id)
        if not current_lock is None: current_lock[0] = 0
        super()._handle_coordinator_update()

    """STATIC METHODS -->"""
    def __lock_get_key(self) -> str:
        return f"{self.LOCK_PREFIX}{self.node_id}"
   
    def __lock_set(self) -> None:
        lock_key     = self.__lock_get_key()
        current_lock = self.coordinator.switch_lock.get(lock_key)
        if current_lock is None : self.coordinator.switch_lock[lock_key] = [0, 1]
        else:
            current_lock[0] = 0
            current_lock[1] += 1

    def __lock_reset(self) -> None:
        lock_key     = self.__lock_get_key()
        current_lock = self.coordinator.switch_lock.get(lock_key)
        if current_lock is None : self.coordinator.switch_lock[lock_key] = [0, 0]
        else:
            current_lock[0] = 0
            if current_lock[1] != 0: current_lock[1] -= 1

    def __get_coordinator_record(self) -> bool | None :
       return None if self.coordinator.data is None else self.coordinator.data.srs_htr_map.get(self.node_id)

    async def __send_command(self, url:str, key:str, value:str, description: str | None) -> bool :
        await self.coordinator.http_client.send_post(url, {key: value}, description)

    """STATIC METHODS <--"""


    async def set_heater_state(self, state: bool) -> None:
        """Turn the hardware relay ON/OFF using the double-lock protocol."""

        self.__lock_set()
        mem_state = self.calculated_state


        self.calculated_state = state
        self.async_write_ha_state()

        check_dev = False
        try:
            await self.__send_command("/api/heater.cgi", "STATE", "ON" if state else "OFF", f"set_heater_state({state})")
        except Exception as err:
            self.calculated_state = mem_state
            check_dev = True
            if isinstance(err, HomeAssistantError) : raise
            raise HomeAssistantError(f"Failed to send command to Silines controller: {err}") from err        
        finally:
            self.__lock_reset()
            self.coordinator.async_update_listeners()
            if check_dev: self.coordinator.set_sheduled_refresh(0.2, "set_heater_state - check device on command error")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.set_heater_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.set_heater_state(False)
