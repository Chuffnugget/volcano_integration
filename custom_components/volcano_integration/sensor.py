from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import random
import asyncio
from .const import DOMAIN

class RandomNumberSensor(SensorEntity):
    """Sensor to generate random numbers."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the random number sensor."""
        self._hass = hass
        self._state = None
        self._running = True

    @property
    def name(self):
        """Return the name of the sensor."""
        return "Random Number"

    @property
    def state(self):
        """Return the current random number."""
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
            # Update the status sensor
            status_sensor = self._hass.data[DOMAIN].get("status_sensor")
            if status_sensor:
                status_sensor.set_running(True)
            await asyncio.sleep(1)

    def stop(self):
        """Stop the random number generator."""
        self._running = False
        # Update the status sensor
        status_sensor = self._hass.data[DOMAIN].get("status_sensor")
        if status_sensor:
            status_sensor.set_running(False)


class StatusSensor(SensorEntity):
    """Sensor to represent the generator's running status."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the status sensor."""
        self._hass = hass
        self._state = "Disconnected"  # Initial state

    @property
    def name(self):
        """Return the name of the status sensor."""
        return "Generator Status"

    @property
    def state(self):
        """Return the current status."""
        return self._state

    def set_running(self, running: bool):
        """Update the status based on whether the generator is running."""
        self._state = "Connected" if running else "Disconnected"
        self.async_write_ha_state()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the sensors."""
    # Create the random number sensor
    random_sensor = RandomNumberSensor(hass)

    # Create the status sensor
    status_sensor = StatusSensor(hass)
    hass.data[DOMAIN]["status_sensor"] = status_sensor

    async_add_entities([random_sensor, status_sensor])
