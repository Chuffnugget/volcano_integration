"""__init__.py - Volcano Integration for Home Assistant."""
import logging
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from .const import DOMAIN
import voluptuous as vol

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

from .bluetooth_coordinator import VolcanoBTManager
from .const import (
    DOMAIN,
    UUID_PUMP_ON,
    UUID_PUMP_OFF,
    UUID_HEAT_ON,
    UUID_HEAT_OFF,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "button", "number", "switch"]

# -------------------------------------------------
# Existing Service Name Constants
# -------------------------------------------------
SERVICE_CONNECT = "connect"
SERVICE_DISCONNECT = "disconnect"
SERVICE_PUMP_ON = "pump_on"
SERVICE_PUMP_OFF = "pump_off"
SERVICE_HEAT_ON = "heat_on"
SERVICE_HEAT_OFF = "heat_off"
SERVICE_SET_TEMPERATURE = "set_temperature"

# -------------------------------------------------
# NEW Service Name Constants
# -------------------------------------------------
SERVICE_SET_AUTO_SHUTOFF_SETTING = "set_auto_shutoff_setting"
SERVICE_SET_LED_BRIGHTNESS = "set_led_brightness"

# -------------------------------------------------
# Existing set_temperature Schema
# -------------------------------------------------
SET_TEMPERATURE_SCHEMA = vol.Schema({
    vol.Required("temperature"): vol.All(vol.Coerce(int), vol.Range(min=40, max=230)),
    vol.Required("wait_until_reached", default=True): cv.boolean,
})

# -------------------------------------------------
# NEW Services Schemas
# -------------------------------------------------
SET_AUTO_SHUTOFF_SCHEMA = vol.Schema({
    vol.Required("minutes", default=30): vol.All(vol.Coerce(int), vol.Range(min=1, max=240)),
})

SET_LED_BRIGHTNESS_SCHEMA = vol.Schema({
    vol.Required("brightness", default=20): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
})

# CHANGED: Connect Service Schema to 'Required' so the UI shows a checkbox
CONNECT_SCHEMA = vol.Schema({
    vol.Required("wait_until_connected", default=True): cv.boolean,
})

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up integration via YAML (if any)."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up the Volcano Integration from a config entry."""
    _LOGGER.debug("Setting up Volcano Integration from config entry: %s", entry.entry_id)

    bt_address = entry.data.get("bt_address")
    device_name = entry.data.get("device_name", "Volcano Vaporizer")

    manager = VolcanoBTManager(bt_address)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = manager

    # Forward setup to sensor, button, number, switch platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # -------------------------------------------------
    # Existing Services Handlers
    # -------------------------------------------------
    async def handle_connect(call):
        """Handle the connect service."""
        _LOGGER.debug("Service 'connect' called.")
        wait = call.data.get("wait_until_connected", False)
        if not manager._connected:
            await manager.async_user_connect()
            if wait:
                await wait_until_connected(hass, manager)
        else:
            _LOGGER.info("Already connected to the device.")

    async def handle_disconnect(call):
        """Handle the disconnect service."""
        _LOGGER.debug("Service 'disconnect' called.")
        if manager._connected:
            await manager.async_user_disconnect()
        else:
            _LOGGER.info("Device already disconnected.")

    async def handle_pump_on(call):
        """Handle the pump_on service."""
        _LOGGER.debug("Service 'pump_on' called.")
        await manager.write_gatt_command(UUID_PUMP_ON, payload=b"\x01")

    async def handle_pump_off(call):
        """Handle the pump_off service."""
        _LOGGER.debug("Service 'pump_off' called.")
        await manager.write_gatt_command(UUID_PUMP_OFF, payload=b"\x00")

    async def handle_heat_on(call):
        """Handle the heat_on service."""
        _LOGGER.debug("Service 'heat_on' called.")
        await manager.write_gatt_command(UUID_HEAT_ON, payload=b"\x01")

    async def handle_heat_off(call):
        """Handle the heat_off service."""
        _LOGGER.debug("Service 'heat_off' called.")
        await manager.write_gatt_command(UUID_HEAT_OFF, payload=b"\x00")

    async def handle_set_temperature(call):
        """Handle the set_temperature service."""
        temperature = call.data["temperature"]
        wait = call.data["wait_until_reached"]

        _LOGGER.debug(f"Service 'set_temperature' called with temperature={temperature}, wait={wait}")
        await manager.set_heater_temperature(temperature)
        if wait:
            await wait_for_temperature(hass, manager, temperature)

    async def wait_for_temperature(hass: HomeAssistant, manager: VolcanoBTManager, target_temp: int):
        """Wait until the current temperature reaches or exceeds the target temperature."""
        timeout = 300  # 5 minutes
        elapsed_time = 0
        _LOGGER.debug(f"Waiting for temperature to reach {target_temp}°C with timeout {timeout}s")

        while elapsed_time < timeout:
            if manager.current_temperature is not None:
                _LOGGER.debug(
                    f"Current temperature is {manager.current_temperature}°C; target is {target_temp}°C"
                )
                if manager.current_temperature >= target_temp:
                    _LOGGER.info(f"Target temperature {target_temp}°C reached.")
                    return
            else:
                _LOGGER.warning("Current temperature is None; retrying...")

            await asyncio.sleep(0.5)
            elapsed_time += 0.5

        _LOGGER.warning(f"Timeout reached while waiting for temperature {target_temp}°C.")

    # NEW: Wait until connected helper function
    async def wait_until_connected(hass: HomeAssistant, manager: VolcanoBTManager):
        """Wait until the Bluetooth manager is connected."""
        timeout = 30  # 30 seconds
        elapsed_time = 0
        _LOGGER.debug(f"Waiting for Bluetooth to connect with timeout {timeout}s")

        while elapsed_time < timeout:
            if manager.bt_status == "CONNECTED":
                _LOGGER.info("Bluetooth connection established.")
                return
            elif manager.bt_status == "ERROR":
                _LOGGER.warning("Bluetooth connection encountered an error.")
                return
            await asyncio.sleep(0.5)
            elapsed_time += 0.5

        _LOGGER.warning("Timeout reached while waiting for Bluetooth to connect.")

    # -------------------------------------------------
    # NEW Services Handlers
    # -------------------------------------------------
    async def handle_set_auto_shutoff_setting(call):
        """Set the Volcano auto shutoff setting in minutes."""
        minutes = call.data["minutes"]
        _LOGGER.debug(f"Service 'set_auto_shutoff_setting' called with minutes={minutes}")
        await manager.set_auto_shutoff_setting(minutes)

    async def handle_set_led_brightness(call):
        """Set the Volcano LED brightness."""
        brightness = call.data["brightness"]
        _LOGGER.debug(f"Service 'set_led_brightness' called with brightness={brightness}")
        await manager.set_led_brightness(brightness)

    # -------------------------------------------------
    # Register All Services
    # -------------------------------------------------
    hass.services.async_register(DOMAIN, SERVICE_CONNECT, handle_connect, schema=CONNECT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DISCONNECT, handle_disconnect)
    hass.services.async_register(DOMAIN, SERVICE_PUMP_ON, handle_pump_on)
    hass.services.async_register(DOMAIN, SERVICE_PUMP_OFF, handle_pump_off)
    hass.services.async_register(DOMAIN, SERVICE_HEAT_ON, handle_heat_on)
    hass.services.async_register(DOMAIN, SERVICE_HEAT_OFF, handle_heat_off)
    hass.services.async_register(
        DOMAIN, SERVICE_SET_TEMPERATURE, handle_set_temperature, schema=SET_TEMPERATURE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_AUTO_SHUTOFF_SETTING, handle_set_auto_shutoff_setting, schema=SET_AUTO_SHUTOFF_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_LED_BRIGHTNESS, handle_set_led_brightness, schema=SET_LED_BRIGHTNESS_SCHEMA
    )

    # IMPORTANT: No auto-connect call here -> user must trigger connect
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload the Volcano Integration."""
    _LOGGER.debug("Unloading Volcano Integration entry: %s", entry.entry_id)

    manager = hass.data[DOMAIN].pop(entry.entry_id, None)
    if manager:
        await manager.stop()

    # Unregister services
    hass.services.async_remove(DOMAIN, SERVICE_CONNECT)
    hass.services.async_remove(DOMAIN, SERVICE_DISCONNECT)
    hass.services.async_remove(DOMAIN, SERVICE_PUMP_ON)
    hass.services.async_remove(DOMAIN, SERVICE_PUMP_OFF)
    hass.services.async_remove(DOMAIN, SERVICE_HEAT_ON)
    hass.services.async_remove(DOMAIN, SERVICE_HEAT_OFF)
    hass.services.async_remove(DOMAIN, SERVICE_SET_TEMPERATURE)
    hass.services.async_remove(DOMAIN, SERVICE_SET_AUTO_SHUTOFF_SETTING)
    hass.services.async_remove(DOMAIN, SERVICE_SET_LED_BRIGHTNESS)

    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return True
