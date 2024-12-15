from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from .const import DOMAIN

class StartRandomNumberButton(ButtonEntity):
    """Button to start the random number generator."""

    def __init__(self, hass):
        """Initialize the button."""
        self._hass = hass

    @property
    def name(self):
        """Return the name of the button."""
        return "Start Random Number Generator"

    async def async_press(self):
        """Handle button press to start the generator."""
        sensor = self._hass.data[DOMAIN].get("sensor")
        if sensor:
            sensor._running = True
            self._hass.loop.create_task(sensor._generate_random_number())
            # Update status sensor
            status_sensor = self._hass.data[DOMAIN].get("status_sensor")
            if status_sensor:
                status_sensor.set_running(True)


class StopRandomNumberButton(ButtonEntity):
    """Button to stop the random number generator."""

    def __init__(self, hass):
        """Initialize the button."""
        self._hass = hass

    @property
    def name(self):
        """Return the name of the button."""
        return "Stop Random Number Generator"

    async def async_press(self):
        """Handle button press to stop the generator."""
        sensor = self._hass.data[DOMAIN].get("sensor")
        if sensor:
            sensor.stop()
            # Update status sensor
            status_sensor = self._hass.data[DOMAIN].get("status_sensor")
            if status_sensor:
                status_sensor.set_running(False)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the buttons."""
    async_add_entities([StartRandomNumberButton(hass), StopRandomNumberButton(hass)])
