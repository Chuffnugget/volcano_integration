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
    {"name": "BLE Firmware Version", "uuid": "10100004-5354-4f52-5a26-4249434b454c", "update_interval": None, "decode": lambda v: v.decode("utf-8").strip()},
    {"name": "Serial Number", "uuid": "10100008-5354-4f52-5a26-4249434b454c", "update_interval": None, "decode": lambda v: v.decode("utf-8").strip()},
    {"name": "Firmware Version", "uuid": "10100003-5354-4f52-5a26-4249434b454c", "update_interval": None, "decode": lambda v: v.decode("utf-8").strip()},
    {"name": "Auto Shutoff Status", "uuid": "1011000c-5354-4f52-5a26-4249434b454c", "update_interval": None, "decode": lambda v: "Enabled" if v == bytearray([0x01]) else "Disabled"},
    {"name": "Auto Shutoff Setting", "uuid": "1011000d-5354-4f52-5a26-4249434b454c", "update_interval": None, "decode": lambda v: f"{int.from_bytes(v, byteorder='little') // 60} minutes"},

    # Periodic sensors
    {"name": "LCD Brightness", "uuid": "10110005-5354-4f52-5a26-4249434b454c", "update_interval": 2, "decode": lambda v: f"{int.from_bytes(v, byteorder='little')}"},
    {"name": "Hours of Operation", "uuid": "10110015-5354-4f52-5a26-4249434b454c", "update_interval": 60, "decode": lambda v: int.from_bytes(v, byteorder="little")},
    {"name": "Minutes of Operation", "uuid": "10110016-5354-4f52-5a26-4249434b454c", "update_interval": 60, "decode": lambda v: int.from_bytes(v, byteorder="little")},
]

_LOGGER = logging.getLogger(__name__)


class VolcanoBluetoothSensor(SensorEntity):
    """Generic sensor for reading Bluetooth characteristics."""

    def __init__(self, hass: HomeAssistant, name: str, uuid: str, decode, update_interval: int = None):
        """Initialize the sensor."""
        self._hass = hass
        self._name = name
        self._uuid = uuid
        self._decode = decode
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
        """Ensure entity is fully initialized before fetching data."""
        if self._update_interval:
            self._hass.loop.create_task(self._periodic_update())

    async def fetch_data(self, client: BleakClient):
        """Fetch data from the Bluetooth device."""
        try:
            queue = self._hass.data[DOMAIN]["bluetooth_queue"]
            await queue.put(self._uuid)

            async with queue:
                value = await client.read_gatt_char(self._uuid)
                if not value:
                    _LOGGER.error("Empty or unrecognized value for %s (UUID: %s)", self._name, self._uuid)
                    return
                self._state = self._decode(value)
                self.async_write_ha_state()
                _LOGGER.debug("Updated %s: %s", self._name, self._state)
        except Exception as e:
            if "Characteristic" in str(e) and "not found" in str(e):
                _LOGGER.error("Characteristic %s not found for %s. Skipping...", self._uuid, self._name)
            else:
                _LOGGER.error("Error fetching data for %s (UUID: %s): %s", self._name, self._uuid, e)

    async def _periodic_update(self):
        """Update the sensor periodically."""
        while True:
            client = self._hass.data[DOMAIN].get("bluetooth_client")
            if client and client.is_connected:
                await self.fetch_data(client)
            await asyncio.sleep(self._update_interval)


class VolcanoTemperatureSensor(VolcanoBluetoothSensor):
    """Specialized sensor for temperature."""
    @property
    def device_class(self):
        return "temperature"

    @property
    def unit_of_measurement(self):
        return "°C"


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
    """Set up all sensors."""
    hass.data[DOMAIN]["bluetooth_client"] = None
    hass.data[DOMAIN]["bluetooth_queue"] = asyncio.Queue()

    entities = [
        VolcanoTemperatureSensor(hass, "Volcano Current Temperature", "10110001-5354-4f52-5a26-4249434b454c", decode=lambda v: int.from_bytes(v, byteorder="little") / 10.0),
        VolcanoStatusSensor(hass)
    ]

    # On-connect only sensors
    for sensor in SENSORS:
        if sensor["update_interval"] is None:
            entity = VolcanoBluetoothSensor(hass, sensor["name"], sensor["uuid"], sensor["decode"])
            entities.append(entity)

    # Periodic sensors
    for sensor in SENSORS:
        if sensor["update_interval"] is not None:
            entities.append(VolcanoBluetoothSensor(hass, sensor["name"], sensor["uuid"], sensor["decode"], sensor["update_interval"]))

    async_add_entities(entities)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload the integration."""
    client = hass.data[DOMAIN].get("bluetooth_client")
    if client and client.is_connected:
        await client.disconnect()
        _LOGGER.info("Disconnected from Bluetooth device at %s", ADDRESS)
