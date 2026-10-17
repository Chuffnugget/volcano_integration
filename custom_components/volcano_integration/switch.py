"""Expose the Hybrid's vibration setting without changing existing entities."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import VolcanoEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([VolcanoVibrationSwitch(entry.runtime_data, entry)])


class VolcanoVibrationSwitch(VolcanoEntity, SwitchEntity):
    """Confirm the vibration setting through the device's control register."""

    _attr_has_entity_name = True
    _attr_name = "Vibration"
    _attr_icon = "mdi:vibrate"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry, "vibration")

    @property
    def available(self) -> bool:
        return super().available and self.manager.state.vibration is not None

    @property
    def is_on(self) -> bool | None:
        return self.manager.state.vibration

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.manager.set_vibration(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.manager.set_vibration(False)
