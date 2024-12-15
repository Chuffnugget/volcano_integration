# Import asyncio for asynchronous tasks and HomeAssistant core for integration setup
import asyncio
from homeassistant.core import HomeAssistant
from .const import DOMAIN  # Import the DOMAIN constant

# Asynchronous setup function called when the integration is loaded
async def async_setup(hass: HomeAssistant, config: dict):
    """
    Initializes the Volcano Integration without configuration entries.

    :param hass: HomeAssistant core object
    :param config: Configuration dictionary
    """
    hass.data[DOMAIN] = {}  # Create a dictionary to store integration-related data
    return True  # Indicate successful setup

# Asynchronous setup function for configuration entries
async def async_setup_entry(hass: HomeAssistant, entry):
    """
    Setup integration using the configuration entry.

    :param hass: HomeAssistant core object
    :param entry: Configuration entry created by the user
    """
    # Forward configuration to specific platforms
    hass.async_create_task(hass.config_entries.async_forward_entry_setup(entry, "sensor"))
    hass.async_create_task(hass.config_entries.async_forward_entry_setup(entry, "button"))
    return True

# Asynchronous function to unload the integration when removed
async def async_unload_entry(hass: HomeAssistant, entry):
    """
    Clean up resources when the configuration entry is removed.

    :param hass: HomeAssistant core object
    :param entry: Configuration entry to be removed
    """
    # Unload the sensor and button platforms
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    await hass.config_entries.async_forward_entry_unload(entry, "button")
    return True
