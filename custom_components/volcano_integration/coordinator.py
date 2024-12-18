# coordinator.py
"""Coordinator for Volcano Integration."""

import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .device import VolcanoBTDevice

_LOGGER = logging.getLogger(__name__)


class VolcanoCoordinator(DataUpdateCoordinator):
    """DataUpdateCoordinator for Volcano Bluetooth devices."""

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
        self.bt_device = VolcanoBTDevice(ble_device)

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
        # For example, read temperature from a GATT characteristic
        temperature_uuid = "YOUR_TEMPERATURE_UUID"
        try:
            raw_data = await self.bt_device.read_gatt_char(temperature_uuid)
            # Process raw_data to extract temperature
            temperature = self.process_temperature_data(raw_data)
            return {"temperature": temperature}
        except Exception as e:
            _LOGGER.error("Error fetching data from device: %s", e)
            return {}

    def process_temperature_data(self, raw_data: bytes) -> float:
        """Process raw temperature data from the device."""
        # Implement the actual processing based on your device's data format
        # Example: Convert bytes to float
        if len(raw_data) >= 2:
            temperature = int.from_bytes(raw_data[:2], byteorder='little') / 100
            return temperature
        return 0.0

    async def wait_ready(self) -> bool:
        """Wait until the device is ready."""
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=30)
            return True
        except asyncio.TimeoutError:
            _LOGGER.error("Device did not become ready within timeout")
            return False
