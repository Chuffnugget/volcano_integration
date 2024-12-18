"""Constants for Volcano Integration."""

import voluptuous as vol
from enum import Enum

from homeassistant.helpers.config_validation import make_entity_service_schema
import homeassistant.helpers.config_validation as cv

DOMAIN = "volcano_integration"
CONF_ADDRESS = "address"
DEVICE_STARTUP_TIMEOUT_SECONDS = 30

# UUIDs for specific functionalities
UUID_TEMPERATURE = "10110001-5354-4f52-5a26-4249434b454c"
UUID_HEAT_ON = "1011000f-5354-4f52-5a26-4249434b454c"
UUID_HEAT_OFF = "10110010-5354-4f52-5a26-4249434b454c"

class Schema(Enum):
    """General used service schema definition"""

    WRITE_GATT = make_entity_service_schema(
        {
            vol.Required("target_uuid"): cv.string,
            vol.Required("data"): cv.string
        }
    )
    READ_GATT = make_entity_service_schema(
        {
            vol.Required("target_uuid"): cv.string
        }
    )
