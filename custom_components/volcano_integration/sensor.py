from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from bleak import BleakClient
import asyncio
import logging
from .const import DOMAIN

ADDRESS = "CE:9E:A6:43:25:F3"  # Bluetooth device address

SENSORS = [
    # On-connect only sensors
    {"name": "BLE Firmware Version", "uuid": "10100004-5354-4f52-5a26-4249434b454c", "update_interval": None},
    {"name": "Serial Number", "uuid": "10100008-5354-4f52-5a26-4249434b454c", "update_interval": None},
    {"name": "Firmware Version", "uuid": "10100003-5354-4f52-5a26-4249434b454c", "update_interval": None},
    {"name": "BLE Device UUID", "uuid": "00000000-0000-0000-0000-000000000420", "update_interval": None},

    # Periodic sensors
    {"name": "LCD Brightness", "uuid": "10110005-5354-4f52-5a26-4249434b454c", "update_interval": 2},
    {"name": "Hours of Operation", "uuid": "10110015-5354-4f52-5a26-4249434b454c", "update_interval": 60},
    {"name": "Minutes of Operation", "uuid": "10110016-5354-4f52-5a26-4249434b454c", "update_interval": 60},
]

_LOGGER = logging.getLogger(__name__)


class VolcanoBluetoothSensor(SensorEntity):
    """Generic sensor for reading Bluetooth characteristics."""

    def __init__(self, hass: HomeAssistant, name: str, uuid: str, client: BleakClient, update_interval: int = None):
        """Initialize the sensor."""
        self._hass = hass
        self._name = name
        self._uuid = uuid
        self._client = client
        self._update_interval = update_interval
        self._state = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    async def async_added_to_hass(self):
        """Called when the entity is added to Home Assistant."""
        if self._update_interval:
            self._hass.loop.create_task(self._periodic_update())

    async def fetch_data(self):
        """Fetch data from the Bluetooth device."""
        try:
            value = await self._client.read_gatt_char(self._uuid)
            self._state = value.decode("utf-8").strip()  # Decode as UTF-8 string for general sensors
            self.async_write_ha_state()
            _LOGGER.debug("Updated %s: %s", self._name, self._state)
        except Exception as e:
            _LOGGER.error("Error fetching data for %s: %s", self._name, e)

    async def _periodic_update(self):
        """Update the sensor periodically."""
        while True:
            await self.fetch_data()
            await asyncio.sleep(self._update_interval)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up all sensors."""
    client = BleakClient(ADDRESS)
    await client.connect()
    _LOGGER.info("Connected to Bluetooth device at %s", ADDRESS)

    entities = []

    # Fetch on-connect only sensors
    for sensor in SENSORS:
        if sensor["update_interval"] is None:
            entity = VolcanoBluetoothSensor(hass, sensor["name"], sensor["uuid"], client)
            await entity.fetch_data()  # Fetch data immediately
            entities.append(entity)

    # Set up periodic sensors
    for sensor in SENSORS:
        if sensor["update_interval"] is not None:
            entities.append(VolcanoBluetoothSensor(hass, sensor["name"], sensor["uuid"], client, sensor["update_interval"]))

    async_add_entities(entities)

    # Ensure client disconnects on unload
    hass.data[DOMAIN]["bluetooth_client"] = client


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload the integration."""
    client = hass.data[DOMAIN].get("bluetooth_client")
    if client and client.is_connected:
        await client.disconnect()
        _LOGGER.info("Disconnected from Bluetooth device at %s", ADDRESS)
