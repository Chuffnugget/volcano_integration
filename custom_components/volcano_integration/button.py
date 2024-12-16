from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from .const import DOMAIN

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
        sensor = self._hass.data[DOMAIN].get("sensor")
        if sensor:
            await sensor.connect()


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
        sensor = self._hass.data[DOMAIN].get("sensor")
        if sensor:
            await sensor.disconnect()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the buttons."""
    async_add_entities([ConnectBluetoothButton(hass), DisconnectBluetoothButton(hass)])
