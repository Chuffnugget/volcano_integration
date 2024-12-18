"""Buttons for Volcano Integration."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, UUID_HEAT_ON, UUID_HEAT_OFF
from .coordinator import GenericBTCoordinator
from .entity import GenericBTEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up Buttons for Volcano Integration based on a config entry."""
    coordinator: GenericBTCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        HeatOnButton(coordinator),
        HeatOffButton(coordinator)
    ])

class HeatOnButton(GenericBTEntity, ButtonEntity):
    """Button to turn the heat on."""

    _attr_name = "Heat On"
    _attr_icon = "mdi:fire"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._device.write_gatt(UUID_HEAT_ON, "01")  # Replace "01" with the appropriate command
            _LOGGER.info("Heat turned on")
        except Exception as e:
            _LOGGER.error("Failed to turn heat on: %s", e)

class HeatOffButton(GenericBTEntity, ButtonEntity):
    """Button to turn the heat off."""

    _attr_name = "Heat Off"
    _attr_icon = "mdi:fire-off"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._device.write_gatt(UUID_HEAT_OFF, "00")  # Replace "00" with the appropriate command
            _LOGGER.info("Heat turned off")
        except Exception as e:
            _LOGGER.error("Failed to turn heat off: %s", e)
