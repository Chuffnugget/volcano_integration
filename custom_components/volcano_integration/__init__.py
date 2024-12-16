from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the integration without configuration entries."""
    hass.data[DOMAIN] = {}
    _LOGGER.info("Volcano Integration setup complete.")
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up the integration using a configuration entry."""
    _LOGGER.info("Setting up Volcano Integration entry.")
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "button"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a configuration entry."""
    _LOGGER.info("Unloading Volcano Integration entry.")
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    await hass.config_entries.async_forward_entry_unload(entry, "button")
    _LOGGER.info("Volcano Integration entry unloaded successfully.")
    return True
