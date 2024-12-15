from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN

class RandomNumberSensor(SensorEntity):
    """Represents a sensor that generates random numbers."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the sensor."""
        self._hass = hass
        self._state = None
        self._running = True

    @property
    def name(self):
        """Return the name of the sensor."""
        return "Random Number"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    async def async_added_to_hass(self):
        """Called when the entity is added to Home Assistant."""
        self._hass.data[DOMAIN]["sensor"] = self
        self._running = True
        self._hass.loop.create_task(self._generate_random_number())

    async def _generate_random_number(self):
        """Continuously generate random numbers."""
        while self._running:
            self._state = random.randint(1, 100)
            self.async_write_ha_state()
            await asyncio.sleep(1)

    def stop(self):
        """Stop generating random numbers."""
        self._running = False

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the sensor platform for the integration."""
    sensor = RandomNumberSensor(hass)
    async_add_entities([sensor])
