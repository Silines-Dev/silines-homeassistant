"""Support for Silines relay pulse duration configuration."""

from __future__ import annotations
from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.exceptions import HomeAssistantError
from . import SilinesConfigEntry, SilinesCoordinator
from .entity import SilinesBaseEntity


async def async_setup_entry(hass: HomeAssistant,entry: SilinesConfigEntry,async_add_entities: AddEntitiesCallback,) -> None:
    """Set up Silines pulse duration configuration inputs dynamically from state maps."""
    coordinator = entry.runtime_data
    if not coordinator or not coordinator.data:
        return

    device_state = coordinator.data
    if not device_state.relay_map:
        return

    entities = [
        SilinesPulseDuration(coordinator, relay_id)
        for relay_id in device_state.relay_map.keys()
    ]
    async_add_entities(entities)

class SilinesPulseDuration(RestoreEntity, SilinesBaseEntity, TextEntity):
    """Text entity for setting relay pulse durations in milliseconds with persistent state recovery."""
    __MIN_VALUE :int = 0
    __MAX_VALUE :int = 4294966295

    def __init__(self,coordinator: SilinesCoordinator,relay_id: int,) -> None:
        """Initialize the persistent number entity configuration using unified hardware keys."""
        super().__init__(coordinator)
        self.relay_id = relay_id

        self._attr_unique_id = f"{self.device_prefix}_pulse_duration_{relay_id}"
        self._attr_icon = "mdi:timer-sand"
        self._attr_has_entity_name = True
        self._attr_translation_key = "pulse_duration"
        self.value                 = ""

    @property
    def native_value(self) -> str:
        """Return the current pulse duration from coordinator cache."""
        return self.value

    @property
    def name(self) -> str:
        """Return the clean local name of the parent relay channel resolved from the state map."""
        if not self.coordinator.data is None:
            relay_obj = self.coordinator.data.relay_map.get(self.relay_id)
            if not relay_obj is None:
                name = relay_obj.name.strip();
                if ( name != "" ): return name 
        return f"Relay {self.relay_id}"


    def parseValue (self, value : str) -> int | None:
        if isinstance(value, str):
            try:
                value = value.strip()
                if value != "":
                    value = int(float(value))
                    if value >= self.__MIN_VALUE and value <= self.__MAX_VALUE:
                        return value
            except (Exception):  pass
            return None

    async def async_added_to_hass(self) -> None:
        """Recover cached parameters directly from Home Assistant database storage."""
        await super().async_added_to_hass()

        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

        cahe = await self.async_get_last_state()
        if not cahe is None:
            mem_state = self.parseValue(cahe.state)
            if not mem_state is None:
                self.coordinator.pulse_durations[self.relay_id] = mem_state
                self.value = str(mem_state)
                return
        self.coordinator.pulse_durations[self.relay_id] = 2000
        self.value = "2000"


    async def async_set_value(self, value: str) -> None:
        """Update value storage state attributes upon interface triggers with out-of-bounds safety."""
        parsed_value = self.parseValue(value)

        if not parsed_value is None:
            self.coordinator.pulse_durations[self.relay_id] = parsed_value
            self.value = str(parsed_value)
            self.async_write_ha_state()
        else:
            self.coordinator.pulse_durations[self.relay_id] = None
            self.value = ""
            self.async_write_ha_state()
            raise HomeAssistantError(f"Invalid pulse duration '{value}'. Value must be an integer from {self.__MIN_VALUE} to {self.__MAX_VALUE}")

    @property
    def available(self) -> bool:
        """Verify network accessibility state alongside physical entity data presence."""
        return super().available and not (self.coordinator.data is None) and not (self.coordinator.data.relay_map.get(self.relay_id) is None)
