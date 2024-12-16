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

SETTINGS_SENSORS = [
    {"name": "BLE Firmware Version", "uuid": "10100004-5354-4f52-5a26-4249434b454c", "decode": lambda v: v.decode("utf-8").strip()},
    {"name": "Serial Number", "uuid": "10100008-5354-4f52-5a26-4249434b454c", "decode": lambda v: v.decode("utf-8").strip()},
    {"name": "Firmware Version", "uuid": "10100003-5354-4f52-5a26-4249434b454c", "decode": lambda v: v.decode("utf-8").strip()},
    {"name": "Auto Shutoff Status", "uuid": "1011000c-5354-4f52-5a26-4249434b454c", "decode": lambda v: "Enabled" if v == bytearray([0x01]) else "Disabled"},
    {"name": "Auto Shutoff Setting", "uuid": "1011000d-5354-4f52-5a26-4249434b454c", "decode": lambda v: f"{int.from_bytes(v, byteorder='little') // 60} minutes"},
]

_LOGGER = logging.getLogger(__name__)


class VolcanoTemperatureSensor(SensorEntity):
    """Sensor for current temperature."""

    def __init__(self, hass: HomeAssistant, client: BleakClient):
        """Initialize the temperature sensor."""
        self._hass = hass
        self._client = client
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
            if self._client and self._client.is_connected:
                try:
                    value = await self._client.read_gatt_char(TEMPERATURE_UUID)
                    self._state = int.from_bytes(value, byteorder="little") / 10.0
                    self.async_write_ha_state()
                    _LOGGER.debug("Updated Current Temperature: %.1f °C", self._state)
                except Exception as e:
                    _LOGGER.error("Error reading temperature: %s", e)
            await asyncio.sleep(0.4)


class VolcanoSettingsSensor(SensorEntity):
    """Sensor for on-demand settings."""

    def __init__(self, hass: HomeAssistant, client: BleakClient, name: str, uuid: str, decode):
        """Initialize the settings sensor."""
        self._hass = hass
        self._client = client
        self._name = name
        self._uuid = uuid
        self._decode = decode
        self._state = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the current state."""
        return self._state

    async def fetch_setting(self):
        """Fetch the sensor value."""
        if self._client and self._client.is_connected:
            try:
                value = await self._client.read_gatt_char(self._uuid)
                self._state = self._decode(value)
                self.async_write_ha_state()
                _LOGGER.info("Updated %s: %s", self._name, self._state)
            except Exception as e:
                _LOGGER.error("Error fetching %s: %s", self._name, e)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up sensors for the integration."""
    client = hass.data[DOMAIN].get("bluetooth_client")

    # Create the temperature sensor
    temperature_sensor = VolcanoTemperatureSensor(hass, client)

    # Create the settings sensors
    settings_sensors = [
        VolcanoSettingsSensor(hass, client, sensor["name"], sensor["uuid"], sensor["decode"])
        for sensor in SETTINGS_SENSORS
    ]

    async_add_entities([temperature_sensor] + settings_sensors)

    # Store the sensors for on-demand updates
    hass.data[DOMAIN]["settings_sensors"] = settings_sensors


async def fetch_settings(hass: HomeAssistant):
    """Fetch all settings values."""
    sensors = hass.data[DOMAIN].get("settings_sensors", [])
    for sensor in sensors:
        await sensor.fetch_setting()
