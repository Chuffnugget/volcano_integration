# Import required modules for sensor entity and asynchronous tasks
import asyncio
import random
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from .const import DOMAIN

# Define a sensor class for generating random numbers
class RandomNumberSensor(SensorEntity):
    """
    Represents a sensor that generates random numbers between 1 and 100 every second.
    """

    def __init__(self, hass: HomeAssistant):
        """
        Initialize the sensor.

        :param hass: HomeAssistant core object
        """
        self._hass = hass
        self._state = None  # Current random number state
        self._running = True  # Flag to control the random number generator

    @property
    def name(self):
        """Return the name of the sensor."""
        return "Random Number"

    @property
    def state(self):
        """Return the current state of the sensor."""
        return self._state

    async def async_added_to_hass(self):
        """
        Called when the sensor is added to Home Assistant.
        """
        self._hass.data[DOMAIN]["sensor"] = self  # Register the sensor in the integration data
        self._running = True
        # Start the random number generator loop
        self._hass.loop.create_task(self._generate_random_number())

    async def _generate_random_number(self):
        """
        Continuously generate random numbers every second while running.
        """
        while self._running:
            self._state = random.randint(1, 100)  # Generate a random number
            self.async_write_ha_state()  # Notify Home Assistant of state change
            await asyncio.sleep(1)  # Wait for one second

    def stop(self):
        """Stop the random number generator."""
        self._running = False
