"""Settings stored on the Volcano itself."""

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import VolcanoEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([VolcanoTemperatureUnit(entry.runtime_data, entry)])


class VolcanoTemperatureUnit(VolcanoEntity, SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "Temperature unit"
    _attr_icon = "mdi:temperature-celsius"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = ["°C", "°F"]

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry, "temperature_unit")

    @property
    def current_option(self) -> str | None:
        unit = self.manager.state.temperature_unit
        return f"°{unit}" if unit else None

    async def async_select_option(self, option: str) -> None:
        await self.manager.set_temperature_unit(option.removeprefix("°"))
