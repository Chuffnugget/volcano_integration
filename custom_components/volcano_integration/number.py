"""Platform for number integration - to set heater temperature (40–230 °C)."""
import logging

from homeassistant.components.number import NumberEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity import EntityCategory

from . import DOMAIN
from .bluetooth_coordinator import BT_DEVICE_ADDRESS

_LOGGER = logging.getLogger(__name__)

MIN_TEMP = 40.0
MAX_TEMP = 230.0
DEFAULT_TEMP = 170.0
STEP = 1.0  # 1 °C increments

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Volcano temperature number for a config entry."""
    _LOGGER.debug("Setting up Volcano number for entry: %s", entry.entry_id)

    manager = hass.data[DOMAIN][entry.entry_id]

    entities = [VolcanoHeaterTempNumber(manager)]
    async_add_entities(entities)


class VolcanoHeaterTempNumber(NumberEntity):
    """Number entity for setting the Volcano's heater temperature (40–230 °C)."""

    def __init__(self, manager):
        super().__init__()  # Removed passing manager
        self._manager = manager
        self._attr_name = "Volcano Heater Temperature Setpoint"
        self._attr_unique_id = "volcano_heater_temperature_setpoint"
        self._attr_icon = "mdi:thermometer"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info = {
            "identifiers": {(DOMAIN, BT_DEVICE_ADDRESS)},
            "name": "Volcano Vaporizer",
            "manufacturer": "Storz & Bickel",
            "model": "Volcano Hybrid Vaporizer",
            "sw_version": "1.0.0",
            "via_device": None,
        }

        # Set the allowed range
        self._attr_native_min_value = MIN_TEMP
        self._attr_native_max_value = MAX_TEMP
        self._attr_native_step = STEP
        self._attr_unit_of_measurement = UnitOfTemperature.CELSIUS

        self._temp_value = DEFAULT_TEMP  # Initialize to default

    @property
    def native_value(self):
        """
        Return the current setpoint.
        """
        return self._temp_value

    async def async_set_native_value(self, value: float) -> None:
        """
        Called when the user sets a new temperature in the HA UI.
        """
        clamped_val = max(MIN_TEMP, min(value, MAX_TEMP))
        _LOGGER.debug(
            "User set heater temperature to %.1f °C -> clamped=%.1f",
            value, clamped_val
        )
        self._temp_value = clamped_val

        # Write the setpoint to the device
        await self._manager.set_heater_temperature(clamped_val)

        # Update the state in HA
        self.async_write_ha_state()

    @property
    def available(self):
        """Only available if BLE is connected."""
        return (self._manager.bt_status == "CONNECTED")
