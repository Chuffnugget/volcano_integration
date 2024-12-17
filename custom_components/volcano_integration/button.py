from bleak import BleakClient
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from .bluetooth_queue import BluetoothQueue
from .settings_handler import fetch_settings
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)
ADDRESS = "CE:9E:A6:43:25:F3"

class BluetoothStatusSensor(ButtonEntity):
    """Sensor to show Bluetooth connection status."""

    def __init__(self):
        self._attr_name = "Bluetooth Connection Status"
        self._state = "Disconnected"

    @property
    def state(self):
        return self._state

    def set_status(self, status: str):
        self._state = status
        _LOGGER.info("Bluetooth status updated: %s", status)
        self.async_write_ha_state()

class ConnectBluetoothButton(ButtonEntity):
    """Button to connect to the Bluetooth device."""

    def __init__(self, hass: HomeAssistant, status_sensor: BluetoothStatusSensor):
        self._hass = hass
        self._status_sensor = status_sensor

    @property
    def name(self):
        return "Connect Bluetooth"

    async def async_press(self):
        client = self._hass.data[DOMAIN].get("bluetooth_client")
        if client:
            await client.disconnect()

        client = BleakClient(ADDRESS)
        queue = BluetoothQueue(client, self._status_sensor)
        self._hass.data[DOMAIN]["bluetooth_client"] = client
        self._hass.data[DOMAIN]["bluetooth_queue"] = queue
        await queue.connect()
        await queue.start()

class DisconnectBluetoothButton(ButtonEntity):
    """Button to disconnect from the Bluetooth device."""

    def __init__(self, hass: HomeAssistant, status_sensor: BluetoothStatusSensor):
        self._hass = hass
        self._status_sensor = status_sensor

    @property
    def name(self):
        return "Disconnect Bluetooth"

    async def async_press(self):
        queue = self._hass.data[DOMAIN].get("bluetooth_queue")
        if queue:
            await queue.disconnect()
        self._status_sensor.set_status("Disconnected")

class GetSettingsButton(ButtonEntity):
    """Button to fetch settings values."""

    def __init__(self, hass: HomeAssistant):
        self._hass = hass

    @property
    def name(self):
        return "Get Settings"

    async def async_press(self):
        await fetch_settings(self._hass)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    status_sensor = BluetoothStatusSensor()
    hass.data[DOMAIN]["bluetooth_status_sensor"] = status_sensor
    async_add_entities([
        ConnectBluetoothButton(hass, status_sensor),
        DisconnectBluetoothButton(hass, status_sensor),
        GetSettingsButton(hass),
        status_sensor,
    ])
