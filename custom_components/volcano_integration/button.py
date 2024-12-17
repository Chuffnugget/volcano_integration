from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from bleak import BleakClient
from .bluetooth_queue import BluetoothQueue
from .settings_handler import fetch_settings
from .const import DOMAIN
import logging  # Ensure logging is imported

_LOGGER = logging.getLogger(__name__)  # Logging initialization

ADDRESS = "CE:9E:A6:43:25:F3"

class ConnectBluetoothButton(ButtonEntity):
    """Button to connect to the Bluetooth device."""

    def __init__(self, hass: HomeAssistant):
        self._hass = hass

    @property
    def name(self):
        return "Connect Bluetooth"

    async def async_press(self):
        """Handle button press to connect."""
        client = self._hass.data[DOMAIN].get("bluetooth_client")
        queue = self._hass.data[DOMAIN].get("bluetooth_queue")

        if client is None:
            client = BleakClient(ADDRESS)
            self._hass.data[DOMAIN]["bluetooth_client"] = client

        if queue is None:
            queue = BluetoothQueue(client)
            self._hass.data[DOMAIN]["bluetooth_queue"] = queue
            await queue.start()

        try:
            await queue.connect()
        except Exception as e:
            _LOGGER.error("Failed to connect to Bluetooth: %s", e)


class DisconnectBluetoothButton(ButtonEntity):
    """Button to disconnect from the Bluetooth device."""

    def __init__(self, hass: HomeAssistant):
        self._hass = hass

    @property
    def name(self):
        return "Disconnect Bluetooth"

    async def async_press(self):
        """Handle button press to disconnect."""
        queue = self._hass.data[DOMAIN].get("bluetooth_queue")
        if queue is None:
            _LOGGER.warning("BluetoothQueue is not initialized.")
            return

        try:
            await queue.disconnect()
        except Exception as e:
            _LOGGER.error("Failed to disconnect from Bluetooth: %s", e)


class GetSettingsButton(ButtonEntity):
    """Button to fetch settings values."""

    def __init__(self, hass: HomeAssistant):
        self._hass = hass

    @property
    def name(self):
        return "Get Settings"

    async def async_press(self):
        """Handle button press to fetch settings."""
        _LOGGER.info("Fetching settings values...")
        await fetch_settings(self._hass)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    async_add_entities([
        ConnectBluetoothButton(hass),
        DisconnectBluetoothButton(hass),
        GetSettingsButton(hass),
    ])
