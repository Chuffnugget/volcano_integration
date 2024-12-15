from homeassistant.components.sensor import SensorEntity  # Ensure SensorEntity is imported
from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import random
import asyncio
from .const import DOMAIN

class RandomNumberSensor(SensorEntity):
    """Sensor to generate random numbers."""

    def __init__(self, hass: HomeAssistant):
        self._hass = hass
        self._state = None
        self._running = True

    @property
    def name(self):
        """Return the name of the sensor."""
        return "Random Number"

    @property
    def state(self):
        """Return the current state."""
        return self._state

    async def async_added_to_hass(self):
        """Start generating random numbers when added to Home Assistant."""
        self._hass.data[DOMAIN]["sensor"] = self
        self._running = True
        self._hass.loop.create_task(self._generate_random_number())

    async def _generate_random_number(self):
        """Generate random numbers every second."""
        while self._running:
            self._state = random.randint(1, 100)
            self.async_write_ha_state()
            await asyncio.sleep(1)

    def stop(self):
        """Stop the random number generator."""
        self._running = False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the sensor."""
    sensor = RandomNumberSensor(hass)
    async_add_entities([sensor])
