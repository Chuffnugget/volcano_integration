# coordinator.py
"""Coordinator for Volcano Integration."""

import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .device import GenericBTDevice

_LOGGER = logging.getLogger(__name__)

DEVICE_STARTUP_TIMEOUT_SECONDS = 30  # Adjust as needed

class GenericBTCoordinator(DataUpdateCoordinator):
    """DataUpdateCoordinator for Generic Bluetooth devices."""

    def __init__(self, hass: HomeAssistant, ble_device, device, device_name, base_unique_id):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=device_name,
            update_interval=None  # Handle updates manually
        )
        self.ble_device = ble_device
        self.device = device
        self.device_name = device_name
        self.base_unique_id = base_unique_id
        self._ready_event = asyncio.Event()
        self._was_unavailable = True
        self.bt_device = GenericBTDevice(ble_device)

    async def async_connect(self):
        """Connect to the Bluetooth device."""
        await self.bt_device.connect()
        self._ready_event.set()

    async def async_disconnect(self):
        """Disconnect from the Bluetooth device."""
        await self.bt_device.disconnect()
        self._ready_event.clear()

    async def async_update_data(self):
        """Fetch data from the device."""
        # Implement your data fetching logic here
        # Example: Read temperature from a specific UUID
        try:
            temperature_uuid = "00002a6e-0000-1000-8000-00805f9b34fb"  # Replace with actual UUID
            raw_data = await self.bt_device.read_gatt_char(temperature_uuid)
            temperature = int.from_bytes(raw_data, byteorder='little') / 100  # Example conversion
            return temperature
        except Exception as e:
            _LOGGER.error("Error fetching data from device: %s", e)
            raise

    async def wait_ready(self) -> bool:
        """Wait until the device is ready."""
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=DEVICE_STARTUP_TIMEOUT_SECONDS)
            return True
        except asyncio.TimeoutError:
            _LOGGER.error("Device did not become ready within timeout")
            return False
