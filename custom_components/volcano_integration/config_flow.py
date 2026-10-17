"""Use Home Assistant's shared Bluetooth discovery, including remote proxies."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode

from .const import DOMAIN

REFRESH_OPTION_VALUE = "REFRESH_DEVICE_LIST"


class VolcanoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure one entry per Bluetooth address without opening another scanner."""

    VERSION = 2

    async def async_step_user(self, user_input=None):
        discovered = bluetooth.async_discovered_service_info(self.hass, connectable=True)
        devices = {
            info.address: info for info in discovered if "VOLCANO" in (info.name or "").upper()
        }
        errors = {}
        if user_input is not None:
            address = user_input.get("bt_address") or user_input.get("selected_device")
            if address and address != REFRESH_OPTION_VALUE:
                try:
                    address = cv.matches_regex(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")(
                        address.strip()
                    )
                except vol.Invalid:
                    errors["base"] = "invalid_address"
                else:
                    await self.async_set_unique_id(address.upper())
                    self._abort_if_unique_id_configured()
                    # Entries made before unique IDs were introduced must also deduplicate.
                    if any(
                        entry.data.get("bt_address", "").upper() == address.upper()
                        for entry in self._async_current_entries()
                    ):
                        return self.async_abort(reason="already_configured")
                    info = next(
                        (info for key, info in devices.items() if key.upper() == address.upper()),
                        None,
                    )
                    return self.async_create_entry(
                        title=info.name if info else "Volcano Vaporizer",
                        data={
                            "bt_address": address.upper(),
                            "device_name": info.name if info else "Volcano Vaporizer",
                        },
                    )
        options = [
            {"label": f"{info.name} ({address})", "value": address}
            for address, info in devices.items()
        ]
        options.append({"label": "Refresh device list", "value": REFRESH_OPTION_VALUE})
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional("selected_device"): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                    ),
                    vol.Optional("bt_address"): cv.string,
                }
            ),
            errors=errors,
        )
