from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from .bluetooth_queue import BluetoothQueue
import asyncio
import logging
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

TEMPERATURE_UUID = "10110001-5354-4f52-5a26-4249434b454c"

class PeriodicBluetoothSensor(SensorEntity):
    """Sensor for periodically updated Bluetooth values."""

    def __init__(self, hass: HomeAssistant, name: str, uuid: str, decode, interval: float):
        self._hass = hass
        self._name = name
        self._uuid = uuid
        self._decode = decode
        self._state = None
        self._interval = interval

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    async def async_added_to_hass(self):
        """Start periodic updates."""
        self._hass.loop.create_task(self._periodic_update())

    async def _periodic_update(self):
        """Periodically fetch data from the Bluetooth device."""
        queue: BluetoothQueue = self._hass.data[DOMAIN].get("bluetooth_queue")
        while True:
            try:
                if not queue or not queue.client.is_connected:
                    _LOGGER.warning("%s: Bluetooth is not connected.", self._name)
                    break

                value = await queue.read_gatt_char(self._uuid)
                self._state = self._decode(value)
                self.async_write_ha_state()
                _LOGGER.info("Updated %s: %s", self._name, self._state)

            except Exception as e:
                _LOGGER.error("Error updating %s: %s", self._name, e)

            await asyncio.sleep(self._interval)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    sensors = [
        PeriodicBluetoothSensor(hass, "Volcano Current Temperature", TEMPERATURE_UUID, lambda v: int.from_bytes(v, byteorder="little") / 10, 0.5),
    ]

    async_add_entities(sensors)
    _LOGGER.info("Volcano sensors set up.")
