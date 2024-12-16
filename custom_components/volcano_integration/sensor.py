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

SETTINGS_SENSORS = [
    {"name": "BLE Firmware Version", "uuid": "10100004-5354-4f52-5a26-4249434b454c", "decode": lambda v: v.decode("utf-8").strip()},
    {"name": "Serial Number", "uuid": "10100008-5354-4f52-5a26-4249434b454c", "decode": lambda v: v.decode("utf-8").strip()},
    {"name": "Firmware Version", "uuid": "10100003-5354-4f52-5a26-4249434b454c", "decode": lambda v: v.decode("utf-8").strip()},
    {"name": "Auto Shutoff Status", "uuid": "1011000c-5354-4f52-5a26-4249434b454c", "decode": lambda v: "Enabled" if v == bytearray([0x01]) else "Disabled"},
    {"name": "Auto Shutoff Setting", "uuid": "1011000d-5354-4f52-5a26-4249434b454c", "decode": lambda v: f"{int.from_bytes(v, byteorder='little') // 60} minutes"},
]

_LOGGER = logging.getLogger(__name__)


class BluetoothQueue:
    """Queue to manage Bluetooth GATT requests."""

    def __init__(self, client: BleakClient):
        """Initialize the queue."""
        self.client = client
        self.queue = asyncio.Queue()

    async def read_gatt_char(self, uuid: str):
        """Queue a GATT read request and return the result."""
        future = asyncio.Future()
        await self.queue.put((uuid, future))
        return await future

    async def _process_queue(self):
        """Continuously process queued GATT read requests."""
        while True:
            uuid, future = await self.queue.get()
            try:
                value = await self.client.read_gatt_char(uuid)
                future.set_result(value)
                _LOGGER.debug("Successfully read UUID %s: %s", uuid, value)
            except Exception as e:
                _LOGGER.error("Error reading UUID %s: %s", uuid, e)
                future.set_exception(e)
            finally:
                self.queue.task_done()

    async def start(self):
        """Start the queue processing task."""
        asyncio.create_task(self._process_queue())


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
        queue: BluetoothQueue = self._hass.data[DOMAIN]["bluetooth_queue"]
        while True:
            try:
                value = await queue.read_gatt_char(TEMPERATURE_UUID)
                self._state = int.from_bytes(value, byteorder="little") / 10.0
                self.async_write_ha_state()
                _LOGGER.info("Updated Current Temperature: %.1f °C", self._state)
            except Exception as e:
                _LOGGER.error("Error updating Current Temperature: %s", e)
            await asyncio.sleep(0.5)


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
        """Fetch the sensor value."""
        queue: BluetoothQueue = self._hass.data[DOMAIN]["bluetooth_queue"]
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
    client = hass.data[DOMAIN].get("bluetooth_client")
    if client is None:
        client = BleakClient(ADDRESS)
        await client.connect()
        hass.data[DOMAIN]["bluetooth_client"] = client
        _LOGGER.info("Bluetooth connected to %s", ADDRESS)

    # Start the Bluetooth queue
    bluetooth_queue = BluetoothQueue(client)
    hass.data[DOMAIN]["bluetooth_queue"] = bluetooth_queue
    await bluetooth_queue.start()

    # Create sensors
    temperature_sensor = VolcanoTemperatureSensor(hass)
    settings_sensors = [
        VolcanoSettingsSensor(hass, sensor["name"], sensor["uuid"], sensor["decode"])
        for sensor in SETTINGS_SENSORS
    ]
    hass.data[DOMAIN]["settings_sensors"] = settings_sensors

    async_add_entities([temperature_sensor] + settings_sensors)
