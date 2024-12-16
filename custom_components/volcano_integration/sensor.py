from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from bleak import BleakClient
import asyncio
import logging
from .const import DOMAIN

ADDRESS = "CE:9E:A6:43:25:F3"  # Bluetooth device address
TEMPERATURE_UUID = "10110001-5354-4f52-5a26-4249434b454c"
FAN_ON_UUID = "10110013-5354-4f52-5a26-4249434b454c"
FAN_OFF_UUID = "10110014-5354-4f52-5a26-4249434b454c"
HEAT_ON_UUID = "011000f-5354-4f52-5a26-4249434b454c"
HEAT_OFF_UUID = "10110010-5354-4f52-5a26-4249434b454c"

_LOGGER = logging.getLogger(__name__)


class VolcanoTemperatureSensor(SensorEntity):
    """Sensor for current temperature."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the temperature sensor."""
        self._hass = hass
        self._state = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return "Volcano Current Temperature"

    @property
    def state(self):
        """Return the current temperature."""
        return self._state

    @property
    def device_class(self):
        return "temperature"

    @property
    def unit_of_measurement(self):
        return "°C"

    async def async_added_to_hass(self):
        """Start periodic temperature updates."""
        self._hass.loop.create_task(self._periodic_update())

    async def _periodic_update(self):
        """Periodically update the temperature."""
        while True:
            client = self._hass.data[DOMAIN].get("bluetooth_client")
            if client and client.is_connected:
                try:
                    value = await client.read_gatt_char(TEMPERATURE_UUID)
                    self._state = int.from_bytes(value, byteorder="little") / 10.0
                    self.async_write_ha_state()
                    _LOGGER.debug("Updated Current Temperature: %.1f °C", self._state)
                except Exception as e:
                    _LOGGER.error("Error reading temperature: %s", e)
            await asyncio.sleep(0.5)  # Updated to 0.5 seconds


class VolcanoToggleSensor(SensorEntity):
    """Sensor for combined on/off values (e.g., Fan, Heat)."""

    def __init__(self, hass: HomeAssistant, name: str, on_uuid: str, off_uuid: str):
        """Initialize the toggle sensor."""
        self._hass = hass
        self._name = name
        self._on_uuid = on_uuid
        self._off_uuid = off_uuid
        self._state = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the current state."""
        return self._state

    async def async_added_to_hass(self):
        """Start periodic updates for the toggle sensor."""
        self._hass.loop.create_task(self._periodic_update())

    async def _periodic_update(self):
        """Periodically update the toggle sensor."""
        while True:
            client = self._hass.data[DOMAIN].get("bluetooth_client")
            if client and client.is_connected:
                try:
                    on_value = await client.read_gatt_char(self._on_uuid)
                    off_value = await client.read_gatt_char(self._off_uuid)

                    # Determine the state based on the values
                    if on_value == bytearray([0x01]) and off_value == bytearray([0x00]):
                        self._state = "On"
                    elif on_value == bytearray([0x00]) and off_value == bytearray([0x01]):
                        self._state = "Off"
                    else:
                        self._state = "Unknown"

                    self.async_write_ha_state()
                    _LOGGER.debug("Updated %s: %s", self._name, self._state)
                except Exception as e:
                    _LOGGER.error("Error updating %s: %s", self._name, e)
            await asyncio.sleep(0.5)  # 0.5 seconds update interval


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up sensors for the integration."""
    # Initialize Bluetooth client as None; connection happens on button press
    hass.data[DOMAIN]["bluetooth_client"] = None

    # Create the sensors
    temperature_sensor = VolcanoTemperatureSensor(hass)
    fan_sensor = VolcanoToggleSensor(hass, "Volcano Fan", FAN_ON_UUID, FAN_OFF_UUID)
    heat_sensor = VolcanoToggleSensor(hass, "Volcano Heat", HEAT_ON_UUID, HEAT_OFF_UUID)

    async_add_entities([temperature_sensor, fan_sensor, heat_sensor])
