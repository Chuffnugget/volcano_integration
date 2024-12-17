from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from .bluetooth_queue import BluetoothQueue
import logging
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# UUIDs
TEMPERATURE_UUID = "10110001-5354-4f52-5a26-4249434b454c"
FAN_ON_UUID = "10110013-5354-4f52-5a26-4249434b454c"
FAN_OFF_UUID = "10110014-5354-4f52-5a26-4249434b454c"

class PeriodicBluetoothSensor(SensorEntity):
    """Sensor for periodically updated Bluetooth values."""

    def __init__(self, hass, name, uuid, decode, interval):
        self._hass = hass
        self._name = name
        self._uuid = uuid
        self._decode = decode
        self._interval = interval
        self._state = None

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    async def async_added_to_hass(self):
        self._hass.loop.create_task(self._periodic_update())

    async def _periodic_update(self):
        queue: BluetoothQueue = self._hass.data[DOMAIN].get("bluetooth_queue")
        while True:
            try:
                value = await queue.read_gatt_char(self._uuid)
                self._state = self._decode(value)
                self.async_write_ha_state()
            except Exception as e:
                _LOGGER.error("Error updating %s: %s", self._name, e)
            await asyncio.sleep(self._interval)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    sensors = [
        PeriodicBluetoothSensor(hass, "Volcano Temperature", TEMPERATURE_UUID, lambda v: int.from_bytes(v, "little") / 10, 0.5),
    ]
    async_add_entities(sensors)
