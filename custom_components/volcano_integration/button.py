# button.py
"""Button platform for Volcano Integration."""

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VolcanoCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Volcano Integration buttons based on a config entry."""
    coordinator: VolcanoCoordinator = hass.data[DOMAIN][entry.entry_id]

    buttons = [
        VolcanoHeatOnButton(coordinator),
        VolcanoHeatOffButton(coordinator),
        # Add more buttons as needed
    ]

    async_add_entities(buttons)


class VolcanoHeatOnButton(CoordinatorEntity, ButtonEntity):
    """Representation of a Volcano Heat On Button."""

    def __init__(self, coordinator: VolcanoCoordinator):
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_name = "Volcano Heat On"
        self._attr_unique_id = f"{coordinator.base_unique_id}_heat_on"

    async def async_press(self) -> None:
        """Handle the button press."""
        heat_on_uuid = "YOUR_HEAT_ON_UUID"
        try:
            await self.coordinator.bt_device.write_gatt_char(heat_on_uuid, bytearray([1]))
            _LOGGER.debug("Sent Heat On command")
        except Exception as e:
            _LOGGER.error("Failed to send Heat On command: %s", e)


class VolcanoHeatOffButton(CoordinatorEntity, ButtonEntity):
    """Representation of a Volcano Heat Off Button."""

    def __init__(self, coordinator: VolcanoCoordinator):
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_name = "Volcano Heat Off"
        self._attr_unique_id = f"{coordinator.base_unique_id}_heat_off"

    async def async_press(self) -> None:
        """Handle the button press."""
        heat_off_uuid = "YOUR_HEAT_OFF_UUID"
        try:
            await self.coordinator.bt_device.write_gatt_char(heat_off_uuid, bytearray([0]))
            _LOGGER.debug("Sent Heat Off command")
        except Exception as e:
            _LOGGER.error("Failed to send Heat Off command: %s", e)
