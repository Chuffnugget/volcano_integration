# binary_sensor.py
"""Binary Sensor platform for Volcano Integration."""

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GenericBTCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Volcano Integration binary sensors based on a config entry."""
    coordinator: GenericBTCoordinator = hass.data[DOMAIN][entry.entry_id]

    binary_sensors = [
        VolcanoHeatStatusBinarySensor(coordinator),
        # Add more binary sensors as needed
    ]

    async_add_entities(binary_sensors)


class VolcanoHeatStatusBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a Volcano Heat Status Binary Sensor."""

    def __init__(self, coordinator: GenericBTCoordinator):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_name = "Volcano Heat Status"
        self._attr_unique_id = f"{coordinator.base_unique_id}_heat_status"
        self._attr_device_class = "power"

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        data = self.coordinator.data
        return data.get("heat_status", False)
