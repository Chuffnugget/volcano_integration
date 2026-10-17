"""Shared entity identity, availability and push subscriptions."""

from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo, Entity

from .bluetooth_coordinator import VolcanoBTManager
from .const import DOMAIN


class VolcanoEntity(Entity):
    """An entity backed by one device snapshot, with no extra HA polling."""

    _attr_should_poll = False

    def __init__(self, manager: VolcanoBTManager, entry, unique_key: str) -> None:
        self.manager = manager
        self._entry = entry
        # Keep the original address spelling so existing entity IDs survive.
        self._attr_unique_id = f"volcano_{unique_key}_{manager.bt_address}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.manager.bt_address)},
            name=self._entry.data.get("device_name", "Volcano Vaporizer"),
            manufacturer="Storz & Bickel",
            model="Volcano Hybrid Vaporizer",
            sw_version=self.manager.state.firmware_version,
        )

    @property
    def available(self) -> bool:
        return self.manager.connected

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.manager.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
