from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN

class StartRandomNumberButton(ButtonEntity):
    """Button to start the random number generator."""

    def __init__(self, hass):
        self._hass = hass

    @property
    def name(self):
        """Return the name of the button."""
        return "Start Random Number Generator"

    async def async_press(self):
        """Start the random number generator."""
        sensor = self._hass.data[DOMAIN].get("sensor")
        if sensor:
            sensor._running = True
            self._hass.loop.create_task(sensor._generate_random_number())

class StopRandomNumberButton(ButtonEntity):
    """Button to stop the random number generator."""

    def __init__(self, hass):
        self._hass = hass

    @property
    def name(self):
        """Return the name of the button."""
        return "Stop Random Number Generator"

    async def async_press(self):
        """Stop the random number generator."""
        sensor = self._hass.data[DOMAIN].get("sensor")
        if sensor:
            sensor.stop()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the buttons."""
    async_add_entities([StartRandomNumberButton(hass), StopRandomNumberButton(hass)])
