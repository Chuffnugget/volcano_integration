# sensor.py
"""Sensor platform for Volcano Integration."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import TEMP_CELSIUS
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant

from .coordinator import GenericBTCoordinator
from .const import DOMAIN, UUID_TEMPERATURE

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up the Volcano sensors."""
    coordinator: GenericBTCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([VolcanoTemperatureSensor(coordinator)], True)

class VolcanoTemperatureSensor(SensorEntity):
    """Representation of a Volcano Temperature Sensor."""

    def __init__(self, coordinator: GenericBTCoordinator):
        """Initialize the sensor."""
        self.coordinator = coordinator
        self._attr_name = f"{coordinator.device_name} Temperature"
        self._attr_unique_id = f"{coordinator.base_unique_id}_temperature"
        self._attr_unit_of_measurement = TEMP_CELSIUS
        self._attr_device_class = "temperature"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.coordinator.data

    async def async_added_to_hass(self):
        """Register update callback."""
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))
        await self.coordinator.async_refresh()
