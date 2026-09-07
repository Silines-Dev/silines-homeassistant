"""Support for Silines pulse buttons."""

from __future__ import annotations
from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from . import SilinesConfigEntry, SilinesCoordinator
from .entity import SilinesBaseEntity

async def async_setup_entry(
    hass: HomeAssistant,
    entry: SilinesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Silines pulse buttons dynamically from coordinator universal data maps."""
    coordinator = entry.runtime_data
    if not coordinator or not coordinator.data:
        return

    device_state = coordinator.data
    if not device_state.relay_map:
        return

    entities = [
        SilinesPulseButton(coordinator, relay_id)
        for relay_id in device_state.relay_map.keys()
    ]
    async_add_entities(entities)


class SilinesPulseButton(SilinesBaseEntity, ButtonEntity):
    """Button entity representing a pulse trigger service on a Silines relay."""

    def __init__(
        self,
        coordinator: SilinesCoordinator,
        relay_id: int,
    ) -> None:
        """Initialize the pulse button entity using unified map keys."""
        super().__init__(coordinator)
        self.relay_id = relay_id
        self._attr_unique_id = f"{self.device_prefix}_pulse_{relay_id}"
        self._attr_icon = "mdi:pulse"
        self._attr_has_entity_name = True
        self._attr_translation_key = "pulse_button"

    @property
    def name(self) -> str | None:
        """Return the dynamic name of the parent relay channel resolved from the state map."""
        if not self.coordinator.data:
            return f"Relay {self.relay_id}"

        relay_obj = self.coordinator.data.relay_map.get(self.relay_id)
        return relay_obj.name if (relay_obj and relay_obj.name) else f"Relay {self.relay_id}"

    @property
    def available(self) -> bool:
        """Verify network accessibility state alongside hardware availability flags."""
        if not super().available or not self.coordinator.data:
            return False

        relay_obj = self.coordinator.data.relay_map.get(self.relay_id)
        return bool(relay_obj and relay_obj.available)

    async def async_press(self) -> None:
        """Handle execution sequence by directly invoking the parent relay's high-performance pulse method."""
        duration      = self.coordinator.pulse_durations.get(self.relay_id)
        switch_entity = self.coordinator.relay_switches.get(self.relay_id)
        
        if not (switch_entity is None) and not (duration is None):
            await switch_entity.async_pulse(duration)
