import logging
from homeassistant.core import HomeAssistant
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def fetch_settings(hass: HomeAssistant):
    """Fetch all settings values."""
    sensors = hass.data[DOMAIN].get("settings_sensors", [])
    for sensor in sensors:
        try:
            await sensor.fetch_setting()
            _LOGGER.info("Fetched value for %s", sensor.name)
        except Exception as e:
            _LOGGER.error("Error fetching value for %s: %s", sensor.name, e)
