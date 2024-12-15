# Import required modules for button entities
from homeassistant.components.button import ButtonEntity
from .const import DOMAIN

# Define a button to start the random number generator
class StartRandomNumberButton(ButtonEntity):
    """
    Button to start the random number generator.
    """

    def __init__(self, hass):
        """
        Initialize the button.

        :param hass: HomeAssistant core object
        """
        self._hass = hass

    @property
    def name(self):
        """Return the name of the button."""
        return "Start Random Number Generator"

    async def async_press(self):
        """
        Handle button press to start the random number generator.
        """
        sensor = self._hass.data[DOMAIN].get("sensor")
        if sensor:
            sensor._running = True
            # Restart the random number generator loop
            self._hass.loop.create_task(sensor._generate_random_number())

# Define a button to stop the random number generator
class StopRandomNumberButton(ButtonEntity):
    """
    Button to stop the random number generator.
    """

    def __init__(self, hass):
        """
        Initialize the button.

        :param hass: HomeAssistant core object
        """
        self._hass = hass

    @property
    def name(self):
        """Return the name of the button."""
        return "Stop Random Number Generator"

    async def async_press(self):
        """
        Handle button press to stop the random number generator.
        """
        sensor = self._hass.data[DOMAIN].get("sensor")
        if sensor:
            sensor.stop()
