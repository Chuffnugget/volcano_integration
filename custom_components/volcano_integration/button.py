"""Platform for button integration. Adds Pump/Heat On/Off in addition to Connect/Disconnect."""
import logging

from homeassistant.components.button import ButtonEntity
from . import DOMAIN
from .bluetooth_coordinator import VolcanoBTManager, BT_DEVICE_ADDRESS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Volcano buttons for a config entry."""
    _LOGGER.debug("Setting up Volcano buttons for entry: %s", entry.entry_id)

    manager: VolcanoBTManager = hass.data[DOMAIN][entry.entry_id]

    entities = [
        VolcanoConnectButton(manager),
        VolcanoDisconnectButton(manager),
        # Pump/Heat GATT write buttons
        VolcanoPumpOnButton(manager),
        VolcanoPumpOffButton(manager),
        VolcanoHeatOnButton(manager),
        VolcanoHeatOffButton(manager),
    ]
    async_add_entities(entities)


class VolcanoBaseButton(ButtonEntity):
    """Base button for the Volcano integration that references the BT manager."""

    def __init__(self, manager: VolcanoBTManager):
        self._manager = manager
        self._attr_device_info = {
            "identifiers": {(DOMAIN, BT_DEVICE_ADDRESS)},
            "name": "Volcano Vaporizer",
            "manufacturer": "Storz & Bickel",
            "model": "Volcano Hybrid Vaporizer",
            "sw_version": "1.0.0",
        }

    @property
    def available(self):
        """Buttons are always available for user interaction."""
        return True


class VolcanoConnectButton(VolcanoBaseButton):
    """A button to force the Volcano integration to connect BLE."""

    def __init__(self, manager: VolcanoBTManager):
        super().__init__(manager)
        self._attr_name = "Volcano Connect"
        self._attr_unique_id = "volcano_connect_button"
        self._attr_icon = "mdi:bluetooth-connect"

    async def async_press(self):
        """Handle the button press for connecting."""
        _LOGGER.debug("VolcanoConnectButton: pressed by user.")
        await self._manager.async_user_connect()


class VolcanoDisconnectButton(VolcanoBaseButton):
    """A button to force the Volcano integration to disconnect BLE."""

    def __init__(self, manager: VolcanoBTManager):
        super().__init__(manager)
        self._attr_name = "Volcano Disconnect"
        self._attr_unique_id = "volcano_disconnect_button"
        self._attr_icon = "mdi:bluetooth-off"

    async def async_press(self):
        """Handle the button press for disconnecting."""
        _LOGGER.debug("VolcanoDisconnectButton: pressed by user.")
        await self._manager.async_user_disconnect()


# ---------------------------------------------------------------------------
# Pump On/Off Buttons
# ---------------------------------------------------------------------------
class VolcanoPumpOnButton(VolcanoBaseButton):
    """A button to turn Pump ON by writing to a GATT characteristic."""

    def __init__(self, manager: VolcanoBTManager):
        super().__init__(manager)
        self._attr_name = "Volcano Pump On"
        self._attr_unique_id = "volcano_pump_on_button"
        self._attr_icon = "mdi:air-purifier"

    async def async_press(self):
        """Handle the button press for turning pump ON."""
        _LOGGER.debug("VolcanoPumpOnButton: pressed by user.")
        await self._manager.write_gatt_command(self._manager.UUID_PUMP_ON, payload=b"\x01")


class VolcanoPumpOffButton(VolcanoBaseButton):
    """A button to turn Pump OFF by writing to a GATT characteristic."""

    def __init__(self, manager: VolcanoBTManager):
        super().__init__(manager)
        self._attr_name = "Volcano Pump Off"
        self._attr_unique_id = "volcano_pump_off_button"
        self._attr_icon = "mdi:air-purifier-off"

    async def async_press(self):
        """Handle the button press for turning pump OFF."""
        _LOGGER.debug("VolcanoPumpOffButton: pressed by user.")
        await self._manager.write_gatt_command(self._manager.UUID_PUMP_OFF, payload=b"\x00")


# ---------------------------------------------------------------------------
# Heat On/Off Buttons
# ---------------------------------------------------------------------------
class VolcanoHeatOnButton(VolcanoBaseButton):
    """A button to turn Heat ON by writing to a GATT characteristic."""

    def __init__(self, manager: VolcanoBTManager):
        super().__init__(manager)
        self._attr_name = "Volcano Heat On"
        self._attr_unique_id = "volcano_heat_on_button"
        self._attr_icon = "mdi:fire"

    async def async_press(self):
        """Handle the button press for turning heat ON."""
        _LOGGER.debug("VolcanoHeatOnButton: pressed by user.")
        await self._manager.write_gatt_command(self._manager.UUID_HEAT_ON, payload=b"\x01")


class VolcanoHeatOffButton(VolcanoBaseButton):
    """A button to turn Heat OFF by writing to a GATT characteristic."""

    def __init__(self, manager: VolcanoBTManager):
        super().__init__(manager)
        self._attr_name = "Volcano Heat Off"
        self._attr_unique_id = "volcano_heat_off_button"
        self._attr_icon = "mdi:fire-off"

    async def async_press(self):
        """Handle the button press for turning heat OFF."""
        _LOGGER.debug("VolcanoHeatOffButton: pressed by user.")
        await self._manager.write_gatt_command(self._manager.UUID_HEAT_OFF, payload=b"\x00")
