"""Base entity specification for the Silines integration."""

from __future__ import annotations
from typing import TYPE_CHECKING
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

if TYPE_CHECKING:
    from .__init__ import SilinesCoordinator


class SilinesBaseEntity(CoordinatorEntity["SilinesCoordinator"]):
    """Common base entity implementation for unified hardware tracking."""

    _attr_has_entity_name = True

    @property
    def device_prefix(self) -> str:
        """Safely resolve device unique prefix directly from config entry data."""
        return self.coordinator.config_entry.unique_id or "fallback_prefix"

    @property
    def device_info(self) -> DeviceInfo:
        """Dynamically assemble DeviceInfo reference linked to the core hardware prefix."""
        if self.coordinator.data:
            device_name = self.coordinator.data.device_name
        else:
            device_name = self.coordinator.config_entry.title

        return DeviceInfo(
            identifiers={(DOMAIN, self.device_prefix)},
            name=device_name,
            manufacturer="Silines",
            model="Silines Controller",
        )
