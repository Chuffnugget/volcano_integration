from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from bleak import BleakClient
from .bluetooth_queue import BluetoothQueue
from .sensor import fetch_settings
from .const import DOMAIN

import logging

ADDRESS = "CE:9E:A6:43:25:F3"

_LOGGER = logging.getLogger(__name__)


class ConnectBluetoothButton(ButtonEntity):
    """Button to connect to the Bluetooth device."""

    def __init__(self, hass: HomeAssistant):
        self._hass = hass

    @property
    def name(self):
        return "Connect Bluetooth"

    async def async_press(self):
        if self._hass.data[DOMAIN].get("bluetooth_client") is not None:
            _LOGGER.warning("Bluetooth is already connected.")
            return

        try:
            client = BleakClient(ADDRESS)
            await client.connect()
            self._hass.data[DOMAIN]["bluetooth_client"] = client

            queue = BluetoothQueue(client)
            self._hass.data[DOMAIN]["bluetooth_queue"] = queue
            await queue.start()

            _LOGGER.info("Connected to Bluetooth device at %s", ADDRESS)
        except Exception as e:
            _LOGGER.error("Failed to connect to Bluetooth device: %s", e)
            self._hass.data[DOMAIN]["bluetooth_client"] = None


class DisconnectBluetoothButton(ButtonEntity):
    """Button to disconnect from the Bluetooth device."""

    def __init__(self, hass: HomeAssistant):
        self._hass = hass

    @property
    def name(self):
        return "Disconnect Bluetooth"

    async def async_press(self):
        client = self._hass.data[DOMAIN].get("bluetooth_client")
        if client and client.is_connected:
            await client.disconnect()
            self._hass.data[DOMAIN]["bluetooth_client"] = None
            self._hass.data[DOMAIN]["bluetooth_queue"] = None
            _LOGGER.info("Disconnected from Bluetooth device.")
        else:
            _LOGGER.warning("Bluetooth is already disconnected.")


class GetSettingsButton(ButtonEntity):
    """Button to fetch settings values."""

    def __init__(self, hass: HomeAssistant):
        self._hass = hass

    @property
    def name(self):
        return "Get Settings"

    async def async_press(self):
        _LOGGER.info("Fetching settings values...")
        await fetch_settings(self._hass)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    async_add_entities([
        ConnectBluetoothButton(hass),
        DisconnectBluetoothButton(hass),
        GetSettingsButton(hass),
    ])
