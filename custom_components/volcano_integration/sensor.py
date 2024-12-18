# sensor.py
"""Sensor platform for Volcano Integration."""

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VolcanoCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Volcano Integration sensors based on a config entry."""
    coordinator: VolcanoCoordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = [
        VolcanoTemperatureSensor(coordinator),
        # Add more sensors as needed
    ]

    async_add_entities(sensors)


class VolcanoTemperatureSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Volcano Temperature Sensor."""

    def __init__(self, coordinator: VolcanoCoordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "Volcano Temperature"
        self._attr_unique_id = f"{coordinator.base_unique_id}_temperature"
        self._attr_native_unit_of_measurement = "°C"
        self._attr_device_class = "temperature"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        data = self.coordinator.data
        return data.get("temperature")
