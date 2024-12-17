from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .bluetooth_queue import BluetoothQueue
import asyncio
import logging
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

TEMPERATURE_UUID = "10110001-5354-4f52-5a26-4249434b454c"
FAN_ON_UUID = "10110013-5354-4f52-5a26-4249434b454c"
FAN_OFF_UUID = "10110014-5354-4f52-5a26-4249434b454c"
HEAT_ON_UUID = "011000f-5354-4f52-5a26-4249434b454c"
HEAT_OFF_UUID = "10110010-5354-4f52-5a26-4249434b454c"


class PeriodicBluetoothSensor(SensorEntity):
    """Sensor for periodically updated Bluetooth values."""

    def __init__(self, hass: HomeAssistant, name: str, uuid: str, decode, interval: float):
        """Initialize the periodic sensor."""
        self._hass = hass
        self._name = name
        self._uuid = uuid
        self._decode = decode
        self._state = None
        self._interval = interval

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the current state."""
        return self._state

    async def async_added_to_hass(self):
        """Start periodic updates when the sensor is added to Home Assistant."""
        self._hass.loop.create_task(self._periodic_update())

    async def _periodic_update(self):
        """Periodically fetch data from the Bluetooth device."""
        queue: BluetoothQueue = self._hass.data[DOMAIN].get("bluetooth_queue")
        while True:
            try:
                if not queue:
                    _LOGGER.warning("%s: BluetoothQueue not available", self._name)
                    break

                value = await queue.read_gatt_char(self._uuid)
                self._state = self._decode(value)
                self.async_write_ha_state()
                _LOGGER.info("Updated %s: %s", self._name, self._state)

            except Exception as e:
                _LOGGER.error("Error updating %s: %s", self._name, e)

            await asyncio.sleep(self._interval)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up sensors for the integration."""
    client = hass.data[DOMAIN].get("bluetooth_client")
    queue = hass.data[DOMAIN].get("bluetooth_queue")

    if client is None or queue is None:
        _LOGGER.warning("Bluetooth client or queue not initialized. Skipping sensor setup.")
        return

    # Create periodic sensors
    periodic_sensors = [
        PeriodicBluetoothSensor(hass, "Volcano Current Temperature", TEMPERATURE_UUID, lambda v: int.from_bytes(v, byteorder="little") / 10, 0.5),
        PeriodicBluetoothSensor(hass, "Volcano Fan Status", FAN_ON_UUID, lambda v: "On" if v == b"\x01" else "Off", 0.5),
        PeriodicBluetoothSensor(hass, "Volcano Heat Status", HEAT_ON_UUID, lambda v: "On" if v == b"\x01" else "Off", 0.5),
    ]

    # Create settings sensors
    settings_sensors = [
        VolcanoSettingsSensor(hass, "BLE Firmware Version", "10100004-5354-4f52-5a26-4249434b454c", lambda v: v.decode("utf-8").strip()),
        VolcanoSettingsSensor(hass, "Serial Number", "10100008-5354-4f52-5a26-4249434b454c", lambda v: v.decode("utf-8").strip()),
    ]

    hass.data[DOMAIN]["settings_sensors"] = settings_sensors

    # Add all entities
    async_add_entities(periodic_sensors + settings_sensors)
    _LOGGER.info("Volcano periodic and settings sensors set up.")
