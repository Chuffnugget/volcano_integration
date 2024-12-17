from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from .bluetooth_queue import BluetoothQueue
import logging
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class VolcanoSettingsSensor(SensorEntity):
    """Sensor for on-demand settings."""

    def __init__(self, hass: HomeAssistant, name: str, uuid: str, decode):
        self._hass = hass
        self._name = name
        self._uuid = uuid
        self._decode = decode
        self._state = None

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    async def fetch_setting(self):
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
    sensors = hass.data[DOMAIN].get("settings_sensors", [])
    for sensor in sensors:
        await sensor.fetch_setting()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    settings_sensors = [
        VolcanoSettingsSensor(hass, sensor["name"], sensor["uuid"], sensor["decode"])
        for sensor in [
            {"name": "BLE Firmware Version", "uuid": "10100004-5354-4f52-5a26-4249434b454c", "decode": lambda v: v.decode("utf-8").strip()},
            {"name": "Serial Number", "uuid": "10100008-5354-4f52-5a26-4249434b454c", "decode": lambda v: v.decode("utf-8").strip()},
        ]
    ]

    hass.data[DOMAIN]["settings_sensors"] = settings_sensors
    async_add_entities(settings_sensors)
