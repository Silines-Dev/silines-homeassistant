"""Support for Silines standard and Hartz climate sensors."""

from __future__ import annotations
import logging
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from . import SilinesConfigEntry, SilinesCoordinator
from .entity import SilinesBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SilinesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Silines sensor platform."""
    coordinator = entry.runtime_data
    if not coordinator or not coordinator.data:
        return

    @callback
    def async_discover_sensors() -> None:
        """Discover and add new sensors dynamically from coordinator data map using composite keys."""
        if not coordinator.data:
            return

        new_entities: list[SilinesEnvironmentSensor] = []

        for hardware_id, sensor_type in coordinator.data.sensor_map:
            registry_key = (hardware_id, sensor_type)
            
            if registry_key not in coordinator.registered_sensor_uids:
                coordinator.registered_sensor_uids.add(registry_key)

                new_entities.append(
                    SilinesEnvironmentSensor(
                        coordinator=coordinator,
                        hardware_id=hardware_id,
                        sensor_type=sensor_type,
                    )
                )

        if new_entities:
            _LOGGER.debug("Discovered %d new Silines sensors", len(new_entities))
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(async_discover_sensors))
    async_discover_sensors()


class SilinesEnvironmentSensor(SilinesBaseEntity, SensorEntity):
    """High-performance environmental entity reading from optimized tuple-mapped models."""

    def __init__(
        self,
        coordinator: SilinesCoordinator,
        hardware_id: str,
        sensor_type: str,
    ) -> None:
        """Initialize the climate sensor properties mapping straight to composite keys."""
        super().__init__(coordinator)
        self.hardware_id = hardware_id
        self.sensor_type = sensor_type

        self._attr_unique_id = f"{self.device_prefix}_{hardware_id.lower()}_{sensor_type.lower()}"
        self._attr_has_entity_name = True
        self._attr_state_class = SensorStateClass.MEASUREMENT

        if sensor_type == "HUM":
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_device_class = SensorDeviceClass.HUMIDITY
            self._attr_icon = "mdi:water-percent"
            self._attr_translation_key = "node_humidity"
        else:
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_icon = "mdi:thermometer"
            self._attr_translation_key = "node_temperature"

    @property
    def name(self) -> str | None:
        """Return the friendly name of the sensor inside the device group."""
        if not self.coordinator.data:
            return self.hardware_id

        sensor_obj = self.coordinator.data.sensor_map.get((self.hardware_id, self.sensor_type))
        base_name = sensor_obj.name if sensor_obj else self.hardware_id
        
        if base_name == self.hardware_id:
            return self.hardware_id
            
        return base_name

    @property
    def native_value(self) -> float | None:
        """Safely extract pre-parsed state values from the coordinator memory maps."""
        if not self.coordinator.data:
            return None

        sensor_obj = self.coordinator.data.sensor_map.get((self.hardware_id, self.sensor_type))
        return sensor_obj.value if sensor_obj else None

    @property
    def available(self) -> bool:
        """Evaluate network availability state alongside physical entity data presence."""
        if not super().available or not self.coordinator.data:
            return False

        sensor_obj = self.coordinator.data.sensor_map.get((self.hardware_id, self.sensor_type))
        return bool(sensor_obj and sensor_obj.valid)
