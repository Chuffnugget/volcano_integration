"""Volcano Integration for Home Assistant."""

import asyncio
import logging

from homeassistant.core import HomeAssistant

from . import device, coordinator

_LOGGER = logging.getLogger(__name__)

DOMAIN = "volcano_integration"

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Volcano Integration."""
    _LOGGER.info("Setting up Volcano Integration")

    # Initialization is handled via config entries
    hass.data[DOMAIN] = {}

    return True

async def async_setup_entry(hass: HomeAssistant, entry):
    """Set up Volcano Integration from a config entry."""
    _LOGGER.info("Setting up Volcano Integration entry")

    address: str = entry.data.get(coordinator.CONF_ADDRESS)
    if not address:
        _LOGGER.error("No Bluetooth address found in config entry")
        return False

    ble_device = await hass.components.bluetooth.async_ble_device_from_address(address.upper(), connectable=True)
    if not ble_device:
        _LOGGER.error("Could not find Bluetooth device with address %s", address)
        return False

    device_instance = device.GenericBTDevice(ble_device)

    coordinator_instance = coordinator.GenericBTCoordinator(
        hass,
        _LOGGER,
        ble_device,
        device_instance,
        entry.title,
        entry.unique_id,
        connectable=True
    )

    await coordinator_instance.initialize()

    hass.data[DOMAIN][entry.entry_id] = coordinator_instance

    if not await coordinator_instance.async_wait_ready():
        _LOGGER.error("Device at address %s is not ready", address)
        return False

    await hass.config_entries.async_forward_entry_setups(entry, ["binary_sensor", "sensor", "button"])

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True

async def _async_update_listener(hass: HomeAssistant, entry):
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["binary_sensor", "sensor", "button"])

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
