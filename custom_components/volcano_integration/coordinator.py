"""Provides the DataUpdateCoordinator for Volcano Integration."""
from __future__ import annotations

import asyncio
import contextlib
import logging

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.active_update_coordinator import ActiveBluetoothDataUpdateCoordinator
from homeassistant.core import CoreState, HomeAssistant, callback
from bleak.backends.device import BLEDevice

from .device import GenericBTDevice
from .const import DOMAIN, DEVICE_STARTUP_TIMEOUT_SECONDS, CONF_ADDRESS

_LOGGER = logging.getLogger(__name__)

class GenericBTCoordinator(ActiveBluetoothDataUpdateCoordinator[None]):
    """Class to manage fetching generic Bluetooth data."""

    def __init__(self, hass: HomeAssistant, logger: logging.Logger, ble_device: BLEDevice, device: GenericBTDevice, device_name: str, base_unique_id: str, connectable: bool) -> None:
        """Initialize global generic Bluetooth data updater."""
        super().__init__(
            hass=hass,
            logger=logger,
            address=ble_device.address,
            needs_poll_method=self._needs_poll,
            poll_method=self._async_update,
            mode=bluetooth.BluetoothScanningMode.ACTIVE,
            connectable=connectable
        )
        self.ble_device = ble_device
        self.device = device
        self.device_name = device_name
        self.base_unique_id = base_unique_id
        self._ready_event = asyncio.Event()
        self._was_unavailable = True

    @callback
    def _needs_poll(self, service_info: bluetooth.BluetoothServiceInfoBleak, seconds_since_last_poll: float | None) -> bool:
        """Determine if polling is needed."""
        return (
            self.hass.state == CoreState.running
            and self.device.poll_needed(seconds_since_last_poll)
            and bool(
                bluetooth.async_ble_device_from_address(
                    self.hass, service_info.device.address, connectable=True
                )
            )
        )

    async def _async_update(self, service_info: bluetooth.BluetoothServiceInfoBleak) -> None:
        """Poll the device."""
        await self.device.update()

    @callback
    def _async_handle_unavailable(self, service_info: bluetooth.BluetoothServiceInfoBleak) -> None:
        """Handle the device going unavailable."""
        super()._async_handle_unavailable(service_info)
        self._was_unavailable = True

    @callback
    def _async_handle_bluetooth_event(self, service_info: bluetooth.BluetoothServiceInfoBleak, change: bluetooth.BluetoothChange) -> None:
        """Handle a Bluetooth event."""
        self.ble_device = service_info.device
        _LOGGER.debug(f"{DOMAIN} - _async_handle_bluetooth_event - {service_info} - {self.ble_device}")
        self._ready_event.set()

        if not self._was_unavailable:
            return

        self._was_unavailable = False
        self.device.update_from_advertisement(service_info.advertisement)
        super()._async_handle_bluetooth_event(service_info, change)

    async def async_wait_ready(self) -> bool:
        """Wait for the device to be ready."""
        with contextlib.suppress(asyncio.TimeoutError):
            async with asyncio.timeout(DEVICE_STARTUP_TIMEOUT_SECONDS):
                await self._ready_event.wait()
                return True
        return False
