"""Platform for number integration - to set heater temperature (40–230 °C) 
   and now LED Brightness (0–100)."""
import logging

from homeassistant.components.number import NumberEntity
from homeassistant.const import UnitOfTemperature

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

MIN_TEMP = 40.0
MAX_TEMP = 230.0
DEFAULT_TEMP = 170.0
STEP = 1.0  # 1 °C increments


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Volcano number entities for a config entry."""
    _LOGGER.debug("Setting up Volcano number for entry: %s", entry.entry_id)

    manager = hass.data[DOMAIN][entry.entry_id]

    # Existing temperature setpoint entity
    entities = [VolcanoHeaterTempNumber(manager, entry)]

    # NEW: Add LED Brightness number writer
    entities.append(VolcanoLEDBrightnessNumber(manager, entry))

    async_add_entities(entities)


class VolcanoHeaterTempNumber(NumberEntity):
    """Number entity for setting the Volcano's heater temperature (40–230 °C)."""

    def __init__(self, manager, config_entry):
        super().__init__()
        self._manager = manager
        self._config_entry = config_entry
        self._attr_name = "Volcano Heater Temperature Setpoint"
        self._attr_unique_id = f"volcano_heater_temperature_setpoint_{self._manager.bt_address}"
        self._attr_icon = "mdi:thermometer"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._manager.bt_address)},
            "name": self._config_entry.data.get("device_name", "Volcano Vaporizer"),
            "manufacturer": "Storz & Bickel",
            "model": "Volcano Hybrid Vaporizer",
            "sw_version": "1.0.0",
            "via_device": None,
        }

        self._attr_native_min_value = MIN_TEMP
        self._attr_native_max_value = MAX_TEMP
        self._attr_native_step = STEP
        self._attr_unit_of_measurement = UnitOfTemperature.CELSIUS

        self._temp_value = DEFAULT_TEMP

    @property
    def native_value(self):
        return self._temp_value

    @property
    def available(self):
        """Available only when Bluetooth is connected."""
        return self._manager.bt_status == "CONNECTED"

    async def async_set_native_value(self, value: float) -> None:
        clamped_val = max(MIN_TEMP, min(value, MAX_TEMP))
        _LOGGER.debug(
            "User set heater temperature to %.1f °C -> clamped=%.1f",
            value,
            clamped_val,
        )
        self._temp_value = clamped_val
        await self._manager.set_heater_temperature(clamped_val)
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Register the temperature setpoint for state updates."""
        _LOGGER.debug("%s added to Home Assistant.", self._attr_name)
        self._manager.register_sensor(self)

    async def async_will_remove_from_hass(self):
        """Unregister the temperature setpoint to stop receiving updates."""
        _LOGGER.debug("%s removed from Home Assistant.", self._attr_name)
        self._manager.unregister_sensor(self)


#
# NEW: Volcano LED Brightness Number
#
class VolcanoLEDBrightnessNumber(NumberEntity):
    """Number entity for setting the Volcano's LED Brightness (0–100)."""

    def __init__(self, manager, config_entry):
        super().__init__()
        self._manager = manager
        self._config_entry = config_entry
        self._attr_name = "Volcano LED Brightness (Writer)"
        self._attr_unique_id = f"volcano_led_brightness_number_{self._manager.bt_address}"
        self._attr_icon = "mdi:brightness-5"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._manager.bt_address)},
            "name": self._config_entry.data.get("device_name", "Volcano Vaporizer"),
            "manufacturer": "Storz & Bickel",
            "model": "Volcano Hybrid Vaporizer",
            "sw_version": "1.0.0",
            "via_device": None,
        }

        # LED Brightness range 0–100
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        # No standard brightness unit in HA; we'll omit or use "percent"
        self._attr_unit_of_measurement = "%"

    @property
    def native_value(self):
        # Return the current brightness stored by the manager
        return self._manager.led_brightness if self._manager.led_brightness is not None else 0

    @property
    def available(self):
        """Available only when Bluetooth is connected."""
        return self._manager.bt_status == "CONNECTED"

    async def async_set_native_value(self, value: float) -> None:
        # Clamp to 0..100 (manager also clamps, but let's do it here as well)
        brightness_int = int(max(0, min(value, 100)))
        _LOGGER.debug(
            "User set LED Brightness to %.1f -> clamped=%d",
            value,
            brightness_int,
        )
        await self._manager.set_led_brightness(brightness_int)
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Register LED brightness for state updates."""
        _LOGGER.debug("%s added to Home Assistant.", self._attr_name)
        self._manager.register_sensor(self)

    async def async_will_remove_from_hass(self):
        """Unregister LED brightness entity to stop receiving updates."""
        _LOGGER.debug("%s removed from Home Assistant.", self._attr_name)
        self._manager.unregister_sensor(self)
