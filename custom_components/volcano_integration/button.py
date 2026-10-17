"""Commands using the existing button identities."""

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription

from .const import UUID_HEAT_OFF, UUID_HEAT_ON, UUID_PUMP_OFF, UUID_PUMP_ON
from .entity import VolcanoEntity


@dataclass(frozen=True, kw_only=True)
class VolcanoButtonDescription(ButtonEntityDescription):
    method: str | None = None
    uuid: str | None = None
    payload: bytes = b""


BUTTONS = (
    VolcanoButtonDescription(
        key="connect",
        name="Volcano Connect",
        icon="mdi:bluetooth-connect",
        method="async_user_connect",
    ),
    VolcanoButtonDescription(
        key="disconnect",
        name="Volcano Disconnect",
        icon="mdi:bluetooth-off",
        method="async_user_disconnect",
    ),
    VolcanoButtonDescription(
        key="pump_on",
        name="Volcano Pump On",
        icon="mdi:air-purifier",
        uuid=UUID_PUMP_ON,
        payload=b"\x01",
    ),
    VolcanoButtonDescription(
        key="pump_off",
        name="Volcano Pump Off",
        icon="mdi:air-purifier-off",
        uuid=UUID_PUMP_OFF,
        payload=b"\x00",
    ),
    VolcanoButtonDescription(
        key="heat_on", name="Volcano Heat On", icon="mdi:fire", uuid=UUID_HEAT_ON, payload=b"\x01"
    ),
    VolcanoButtonDescription(
        key="heat_off",
        name="Volcano Heat Off",
        icon="mdi:fire-off",
        uuid=UUID_HEAT_OFF,
        payload=b"\x00",
    ),
)


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    manager = entry.runtime_data
    async_add_entities(VolcanoButton(manager, entry, description) for description in BUTTONS)


class VolcanoButton(VolcanoEntity, ButtonEntity):
    entity_description: VolcanoButtonDescription

    def __init__(self, manager, entry, description) -> None:
        super().__init__(manager, entry, f"{description.key}_button")
        self.entity_description = description

    @property
    def available(self) -> bool:
        return self.entity_description.method is not None or super().available

    async def async_press(self) -> None:
        description = self.entity_description
        if description.method:
            await getattr(self.manager, description.method)()
        else:
            await self.manager.write_gatt_command(description.uuid, description.payload)
