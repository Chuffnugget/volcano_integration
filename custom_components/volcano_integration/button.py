# button.py
"""Button platform for Volcano Integration."""

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant

from .coordinator import GenericBTCoordinator
from .const import DOMAIN, UUID_HEAT_CONTROL

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up the Volcano buttons."""
    coordinator: GenericBTCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([
        VolcanoHeatOnButton(coordinator),
        VolcanoHeatOffButton(coordinator)
    ], True)

class VolcanoHeatOnButton(ButtonEntity):
    """Button to turn heat on."""

    def __init__(self, coordinator: GenericBTCoordinator):
        """Initialize the button."""
        self.coordinator = coordinator
        self._attr_name = f"{coordinator.device_name} Heat On"
        self._attr_unique_id = f"{coordinator.base_unique_id}_heat_on"

    async def async_press(self):
        """Handle the button press."""
        try:
            # Implement the logic to turn heat on
            # Example: Write a specific value to a GATT characteristic
            await self.coordinator.bt_device.write_gatt_char(UUID_HEAT_CONTROL, b'\x01')
            await self.coordinator.async_refresh()
        except Exception as e:
            _LOGGER.error("Failed to turn heat on: %s", e)

class VolcanoHeatOffButton(ButtonEntity):
    """Button to turn heat off."""

    def __init__(self, coordinator: GenericBTCoordinator):
        """Initialize the button."""
        self.coordinator = coordinator
        self._attr_name = f"{coordinator.device_name} Heat Off"
        self._attr_unique_id = f"{coordinator.base_unique_id}_heat_off"

    async def async_press(self):
        """Handle the button press."""
        try:
            # Implement the logic to turn heat off
            # Example: Write a specific value to a GATT characteristic
            await self.coordinator.bt_device.write_gatt_char(UUID_HEAT_CONTROL, b'\x00')
            await self.coordinator.async_refresh()
        except Exception as e:
            _LOGGER.error("Failed to turn heat off: %s", e)
