"""Sensors for Volcano Integration."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, UUID_HEAT_ON, UUID_HEAT_OFF
from .coordinator import GenericBTCoordinator
from .entity import GenericBTEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up Sensors for Volcano Integration based on a config entry."""
    coordinator: GenericBTCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        CurrentTemperatureSensor(coordinator),
        HeatStatusSensor(coordinator)
    ])

class HeatStatusSensor(GenericBTEntity, SensorEntity):
    """Representation of the Heat Status."""

    _attr_name = "Heat Status"
    _attr_icon = "mdi:fire"
    _attr_state_class = None
    _attr_unit_of_measurement = None

    def __init__(self, coordinator: GenericBTCoordinator) -> None:
        """Initialize the heat status sensor."""
        super().__init__(coordinator)
        self._status = "Unknown"
        self._update_task = asyncio.create_task(self._update_status())

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._status

    async def _update_status(self):
        """Fetch heat status periodically."""
        while True:
            try:
                # Read Heat On UUID
                on_data = await self._device.read_gatt(UUID_HEAT_ON)
                # Read Heat Off UUID
                off_data = await self._device.read_gatt(UUID_HEAT_OFF)

                # Determine heat status based on UUIDs
                if on_data and any(b != 0 for b in on_data):
                    self._status = "On"
                elif off_data and any(b != 0 for b in off_data):
                    self._status = "Off"
                else:
                    self._status = "Unknown"

                self.async_write_ha_state()
            except Exception as e:
                _LOGGER.error("Error reading heat status: %s", e)
            await asyncio.sleep(5)  # Adjust polling interval as needed

    async def async_will_remove_from_hass(self):
        """Cleanup when entity is removed."""
        self._update_task.cancel()
        await super().async_will_remove_from_hass()
