# __init__.py
"""Initialize Volcano Integration."""

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import GenericBTCoordinator
from .device import GenericBTDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Volcano Integration from a config entry."""
    ble_address = entry.data.get("address")
    if not ble_address:
        _LOGGER.error("No Bluetooth address found in config entry.")
        return False

    # Import the async_ble_device_from_address function directly
    from homeassistant.components.bluetooth import async_ble_device_from_address

    try:
        ble_device = await async_ble_device_from_address(
            hass, ble_address, connectable=True
        )
    except Exception as e:
        _LOGGER.error("Error obtaining BLE device: %s", e)
        return False

    if not ble_device:
        _LOGGER.error("Bluetooth device not found: %s", ble_address)
        return False

    device_name = ble_device.name or ble_address
    base_unique_id = f"{DOMAIN}_{ble_address}"

    device = GenericBTDevice(ble_device)

    coordinator = GenericBTCoordinator(
        hass,
        ble_device,
        device,
        device_name,
        base_unique_id
    )

    await coordinator.async_connect()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Set up platforms (sensors, binary sensors, buttons)
    for component in ("sensor", "binary_sensor", "button"):
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: GenericBTCoordinator = hass.data[DOMAIN][entry.entry_id]

    await coordinator.async_disconnect()

    unload_ok = True
    for component in ("sensor", "binary_sensor", "button"):
        unload_ok &= await hass.config_entries.async_forward_entry_unload(entry, component)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
