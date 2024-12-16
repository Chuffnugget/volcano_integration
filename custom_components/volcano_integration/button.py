from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from bleak import BleakClient
import logging
from .sensor import fetch_settings
from .const import DOMAIN

ADDRESS = "CE:9E:A6:43:25:F3"  # Bluetooth device address

_LOGGER = logging.getLogger(__name__)


class ConnectBluetoothButton(ButtonEntity):
    """Button to connect to the Bluetooth device."""

    def __init__(self, hass):
        """Initialize the button."""
        self._hass = hass

    @property
    def name(self):
        """Return the name of the button."""
        return "Connect Bluetooth"

    async def async_press(self):
        """Handle button press to connect."""
        if self._hass.data[DOMAIN].get("bluetooth_client") is not None:
            _LOGGER.warning("Bluetooth is already connected.")
            return

        try:
            client = BleakClient(ADDRESS)
            await client.connect()
            self._hass.data[DOMAIN]["bluetooth_client"] = client
            _LOGGER.info("Connected to Bluetooth device at %s", ADDRESS)

        except Exception as e:
            _LOGGER.error("Failed to connect to Bluetooth device: %s", e)
            self._hass.data[DOMAIN]["bluetooth_client"] = None


class DisconnectBluetoothButton(ButtonEntity):
    """Button to disconnect from the Bluetooth device."""

    def __init__(self, hass):
        """Initialize the button."""
        self._hass = hass

    @property
    def name(self):
        """Return the name of the button."""
        return "Disconnect Bluetooth"

    async def async_press(self):
        """Handle button press to disconnect."""
        client = self._hass.data[DOMAIN].get("bluetooth_client")
        if client is not None and client.is_connected:
            await client.disconnect()
            _LOGGER.info("Disconnected from Bluetooth device at %s", ADDRESS)
            self._hass.data[DOMAIN]["bluetooth_client"] = None
        else:
            _LOGGER.warning("Bluetooth is already disconnected.")


class GetSettingsButton(ButtonEntity):
    """Button to fetch settings values."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the button."""
        self._hass = hass

    @property
    def name(self):
        """Return the name of the button."""
        return "Get Settings"

    async def async_press(self):
        """Handle button press to fetch settings."""
        _LOGGER.info("Fetching settings values...")
        await fetch_settings(self._hass)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the buttons."""
    async_add_entities([
        ConnectBluetoothButton(hass),
        DisconnectBluetoothButton(hass),
        GetSettingsButton(hass),
    ])
