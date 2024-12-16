from homeassistant.components.button import ButtonEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from bleak import BleakClient
import logging
from .const import DOMAIN
from .sensor import fetch_settings

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

            # Update the status sensor
            status_sensor = self._hass.data[DOMAIN].get("status_sensor")
            if status_sensor:
                status_sensor.set_running(True)

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

            # Update the status sensor
            status_sensor = self._hass.data[DOMAIN].get("status_sensor")
            if status_sensor:
                status_sensor.set_running(False)
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
        _LOGGER.info("Settings values fetched successfully.")


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

    async def async_added_to_hass(self):
        """Ensure the sensor is registered with Home Assistant."""
        self._hass.data[DOMAIN]["status_sensor"] = self

    def set_running(self, running: bool):
        """Update the status based on the connection."""
        self._state = "Connected" if running else "Disconnected"
        self.async_write_ha_state()
        _LOGGER.info("Bluetooth status updated: %s", self._state)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the buttons."""
    # Add buttons and status sensor
    async_add_entities([
        ConnectBluetoothButton(hass),
        DisconnectBluetoothButton(hass),
        GetSettingsButton(hass),
        VolcanoStatusSensor(hass)
    ])
