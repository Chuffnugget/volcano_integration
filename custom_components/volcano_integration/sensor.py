from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from bleak import BleakClient
import asyncio
import logging
from .const import DOMAIN

ADDRESS = "CE:9E:A6:43:25:F3"  # Bluetooth device address
TEMPERATURE_CHARACTERISTIC = "10110001-5354-4f52-5a26-4249434b454c"  # GATT characteristic UUID

_LOGGER = logging.getLogger(__name__)

class VolcanoTemperatureSensor(SensorEntity):
    """Sensor to read the current temperature from a Bluetooth device."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the temperature sensor."""
        self._hass = hass
        self._state = None
        self._connected = False
        self._client = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return "Volcano Current Temperature"

    @property
    def state(self):
        """Return the current temperature."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "°C"

    @property
    def device_class(self):
        """Return the device class."""
        return "temperature"

    async def async_added_to_hass(self):
        """Called when the entity is added to Home Assistant."""
        self._hass.data[DOMAIN]["sensor"] = self
        _LOGGER.info("Temperature sensor added to Home Assistant.")

    async def connect(self):
        """Connect to the Bluetooth device."""
        if self._connected:
            _LOGGER.warning("Already connected to the Bluetooth device.")
            return
        try:
            self._client = BleakClient(ADDRESS)
            await self._client.connect()
            self._connected = True
            _LOGGER.info("Connected to Bluetooth device at %s", ADDRESS)
            self._hass.data[DOMAIN]["status_sensor"].set_running(True)
            self._hass.loop.create_task(self._read_temperature())
        except Exception as e:
            self._connected = False
            self._hass.data[DOMAIN]["status_sensor"].set_running(False)
            _LOGGER.error("Failed to connect to Bluetooth device: %s", e)

    async def disconnect(self):
        """Disconnect from the Bluetooth device."""
        if self._connected and self._client:
            await self._client.disconnect()
        self._connected = False
        self._hass.data[DOMAIN]["status_sensor"].set_running(False)
        _LOGGER.info("Disconnected from Bluetooth device at %s", ADDRESS)

    async def _read_temperature(self):
        """Read the temperature every 0.4 seconds."""
        while self._connected:
            try:
                value = await self._client.read_gatt_char(TEMPERATURE_CHARACTERISTIC)
                # Assume the temperature is an integer in °C
                self._state = int.from_bytes(value, byteorder="little")
                self.async_write_ha_state()
                _LOGGER.debug("Temperature updated: %s °C", self._state)
            except Exception as e:
                self._connected = False
                self._hass.data[DOMAIN]["status_sensor"].set_running(False)
                _LOGGER.error("Error reading temperature: %s", e)
            await asyncio.sleep(0.4)


class VolcanoStatusSensor(SensorEntity):
    """Sensor to represent the Bluetooth connection status."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the status sensor."""
        self._hass = hass
        self._state = "Disconnected"

    @property
    def name(self):
        """Return the name of the status sensor."""
        return "Volcano Bluetooth Status"

    @property
    def state(self):
        """Return the current connection status."""
        return self._state

    def set_running(self, running: bool):
        """Update the status based on the connection."""
        self._state = "Connected" if running else "Disconnected"
        self.async_write_ha_state()
        _LOGGER.info("Bluetooth status updated: %s", self._state)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the sensors."""
    temperature_sensor = VolcanoTemperatureSensor(hass)
    status_sensor = VolcanoStatusSensor(hass)

    hass.data[DOMAIN]["sensor"] = temperature_sensor
    hass.data[DOMAIN]["status_sensor"] = status_sensor

    async_add_entities([temperature_sensor, status_sensor])
