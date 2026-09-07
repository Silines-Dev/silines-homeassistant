"""Support for Silines discrete and binary status inputs."""

from __future__ import annotations
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from . import SilinesConfigEntry, SilinesCoordinator
from .entity import SilinesBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SilinesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Silines discrete inputs dynamically from coordinator hardware state maps."""
    coordinator = entry.runtime_data
    if not coordinator or not coordinator.data:
        return

    device_state = coordinator.data
    if not device_state.input_map:
        return

    entities = [
        SilinesInput(coordinator, input_id)
        for input_id in device_state.input_map.keys()
    ]
    async_add_entities(entities)


class SilinesInput(SilinesBaseEntity, BinarySensorEntity):
    """Binary input representation handling tri-state telemetry variables safely."""

    def __init__(
        self,
        coordinator: SilinesCoordinator,
        input_id: int,
    ) -> None:
        """Initialize the binary input entity using unified map keys."""
        super().__init__(coordinator)
        self.input_id = input_id

        self._attr_unique_id = f"{self.device_prefix}_input_{input_id}"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:electric-switch-closed"

    @property
    def name(self) -> str:
        """Return the dynamic name of the binary input channel resolved from the state map."""
        if not self.coordinator.data:
            return f"Input {self.input_id}"

        input_obj = self.coordinator.data.input_map.get(self.input_id)
        return input_obj.name if input_obj else f"Input {self.input_id}"

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is active based on the modern data model."""
        if not self.coordinator.data:
            return None

        input_obj = self.coordinator.data.input_map.get(self.input_id)
        return input_obj.is_on if input_obj else None

    @property
    def available(self) -> bool:
        """Verify network accessibility state alongside physical line validity (Tri-state)."""
        if not super().available or not self.coordinator.data:
            return False

        input_obj = self.coordinator.data.input_map.get(self.input_id)
        return bool(input_obj and input_obj.valid)
