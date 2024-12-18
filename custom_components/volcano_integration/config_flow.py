# config_flow.py
"""Config flow for Volcano Integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from .device import GenericBTDevice

_LOGGER = logging.getLogger(__name__)


class VolcanoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Volcano Integration."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle a discovered Bluetooth device."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name or discovery_info.address
        }
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step to select a device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            discovery_info = self._discovered_devices.get(address)
            if not discovery_info:
                errors["base"] = "not_found"
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._user_schema(),
                    errors=errors,
                )
            device = GenericBTDevice(discovery_info.device)
            try:
                await device.connect()
                await device.disconnect()
            except Exception as e:
                _LOGGER.error("Cannot connect to device: %s", e)
                errors["base"] = "cannot_connect"
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._user_schema(),
                    errors=errors,
                )
            return self.async_create_entry(
                title=discovery_info.name or address,
                data={CONF_ADDRESS: discovery_info.address},
            )

        if self._discovery_info:
            self._discovered_devices[self._discovery_info.address] = self._discovery_info
        else:
            current_addresses = self._async_current_ids()
            async for discovery in async_discovered_service_info(self.hass):
                if (
                    discovery.address in current_addresses
                    or discovery.address in self._discovered_devices
                ):
                    continue
                self._discovered_devices[discovery.address] = discovery

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=self._user_schema(),
            errors=errors,
        )

    def _user_schema(self):
        """Return the user schema."""
        return vol.Schema(
            {
                vol.Required(CONF_ADDRESS): vol.In(
                    {
                        service_info.address: f"{service_info.name or service_info.address} ({service_info.address})"
                        for service_info in self._discovered_devices.values()
                    }
                )
            }
        )
