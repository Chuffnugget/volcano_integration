"""Binary sensors for Volcano Integration."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, Schema
from .coordinator import GenericBTCoordinator
from .entity import GenericBTEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up Binary Sensors for Volcano Integration based on a config entry."""
    coordinator: GenericBTCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        BluetoothStatusSensor(coordinator)
    ])

    platform = hass.helpers.entity_platform.async_get_current_platform()
    platform.async_register_entity_service("write_gatt", Schema.WRITE_GATT.value, "write_gatt")
    platform.async_register_entity_service("read_gatt", Schema.READ_GATT.value, "read_gatt")

class BluetoothStatusSensor(GenericBTEntity, BinarySensorEntity):
    """Representation of a Bluetooth connection status binary sensor."""

    _attr_name = "Bluetooth Status"
    _attr_icon = "mdi:bluetooth"

    @property
    def is_on(self) -> bool:
        """Return True if the device is connected."""
        return self._device.connected
