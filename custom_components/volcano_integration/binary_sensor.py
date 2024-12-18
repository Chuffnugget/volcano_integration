# binary_sensor.py
"""Binary Sensor platform for Volcano Integration."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant

from .coordinator import GenericBTCoordinator
from .const import DOMAIN, UUID_HEAT_CONTROL

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up the Volcano binary sensors."""
    coordinator: GenericBTCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([VolcanoHeatStatusBinarySensor(coordinator)], True)

class VolcanoHeatStatusBinarySensor(BinarySensorEntity):
    """Representation of a Volcano Heat Status Binary Sensor."""

    def __init__(self, coordinator: GenericBTCoordinator):
        """Initialize the binary sensor."""
        self.coordinator = coordinator
        self._attr_name = f"{coordinator.device_name} Heat Status"
        self._attr_unique_id = f"{coordinator.base_unique_id}_heat_status"
        self._attr_device_class = "power"

    @property
    def is_on(self):
        """Return true if the heat is on."""
        # Implement logic to determine heat status from coordinator data
        # Example:
        return bool(self.coordinator.data)

    async def async_added_to_hass(self):
        """Register update callback."""
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))
        await self.coordinator.async_refresh()
