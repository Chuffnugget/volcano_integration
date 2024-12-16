from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import asyncio
import logging
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class VolcanoSettingsSensor(SensorEntity):
    """Sensor for on-demand settings."""

    def __init__(self, hass: HomeAssistant, name: str, uuid: str, decode):
        """Initialize the settings sensor."""
        self._hass = hass
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
        """Fetch the sensor value using the shared Bluetooth client."""
        client = self._hass.data[DOMAIN].get("bluetooth_client")
        queue = self._hass.data[DOMAIN].get("bluetooth_queue")
        if client is None or not client.is_connected:
            _LOGGER.warning("Cannot fetch %s: Bluetooth is not connected.", self._name)
            return

        try:
            value = await queue.read_gatt_char(self._uuid)
            self._state = self._decode(value)
            self.async_write_ha_state()
            _LOGGER.info("Updated %s: %s", self._name, self._state)
        except Exception as e:
            _LOGGER.error("Error fetching %s: %s", self._name, e)


async def fetch_settings(hass: HomeAssistant):
    """Fetch all settings values."""
    sensors = hass.data[DOMAIN].get("settings_sensors", [])
    for sensor in sensors:
        try:
            await sensor.fetch_setting()
            _LOGGER.info("Fetched value for %s", sensor.name)
        except Exception as e:
            _LOGGER.error("Error fetching value for %s: %s", sensor.name, e)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up sensors for the integration."""
    settings_sensors = [
        VolcanoSettingsSensor(hass, sensor["name"], sensor["uuid"], sensor["decode"])
        for sensor in [
            {"name": "BLE Firmware Version", "uuid": "10100004-5354-4f52-5a26-4249434b454c", "decode": lambda v: v.decode("utf-8").strip()},
            {"name": "Serial Number", "uuid": "10100008-5354-4f52-5a26-4249434b454c", "decode": lambda v: v.decode("utf-8").strip()},
            {"name": "Firmware Version", "uuid": "10100003-5354-4f52-5a26-4249434b454c", "decode": lambda v: v.decode("utf-8").strip()},
            {"name": "Auto Shutoff Status", "uuid": "1011000c-5354-4f52-5a26-4249434b454c", "decode": lambda v: "Enabled" if v == bytearray([0x01]) else "Disabled"},
            {"name": "Auto Shutoff Setting", "uuid": "1011000d-5354-4f52-5a26-4249434b454c", "decode": lambda v: f"{int.from_bytes(v, byteorder='little') // 60} minutes"},
        ]
    ]

    # Store settings sensors in hass.data for shared access
    hass.data[DOMAIN]["settings_sensors"] = settings_sensors

    # Add settings sensors
    async_add_entities(settings_sensors)
    _LOGGER.info("Volcano settings sensors set up.")
