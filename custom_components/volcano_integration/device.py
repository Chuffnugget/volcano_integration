# device.py
"""Volcano Integration Bluetooth Device."""

import asyncio
import logging

from bleak import BleakClient
from bleak.exc import BleakError

_LOGGER = logging.getLogger(__name__)


class VolcanoBTDevice:
    """Volcano Bluetooth Device for Volcano Integration."""

    def __init__(self, ble_device):
        """Initialize the Bluetooth device."""
        self._ble_device = ble_device
        self._client = BleakClient(self._ble_device)
        self._lock = asyncio.Lock()

    async def connect(self):
        """Connect to the Bluetooth device."""
        async with self._lock:
            if not self._client.is_connected:
                try:
                    await self._client.connect()
                    _LOGGER.debug("Connected to BLE device: %s", self._ble_device.address)
                except BleakError as e:
                    _LOGGER.error("Failed to connect to BLE device: %s", e)
                    raise
                except Exception as e:
                    _LOGGER.exception("Unexpected error during BLE connection: %s", e)
                    raise

    async def disconnect(self):
        """Disconnect from the Bluetooth device."""
        async with self._lock:
            if self._client.is_connected:
                try:
                    await self._client.disconnect()
                    _LOGGER.debug("Disconnected from BLE device: %s", self._ble_device.address)
                except BleakError as e:
                    _LOGGER.error("Failed to disconnect BLE device: %s", e)
                    raise
                except Exception as e:
                    _LOGGER.exception("Unexpected error during BLE disconnection: %s", e)
                    raise

    async def write_gatt_char(self, uuid, data, response=True):
        """Write data to a GATT characteristic."""
        async with self._lock:
            try:
                await self._client.write_gatt_char(uuid, data, response=response)
                _LOGGER.debug("Wrote data to UUID %s: %s", uuid, data)
            except BleakError as e:
                _LOGGER.error("Failed to write to GATT characteristic %s: %s", uuid, e)
                raise
            except Exception as e:
                _LOGGER.exception("Unexpected error during GATT write: %s", e)
                raise

    async def read_gatt_char(self, uuid):
        """Read data from a GATT characteristic."""
        async with self._lock:
            try:
                data = await self._client.read_gatt_char(uuid)
                _LOGGER.debug("Read data from UUID %s: %s", uuid, data)
                return data
            except BleakError as e:
                _LOGGER.error("Failed to read from GATT characteristic %s: %s", uuid, e)
                raise
            except Exception as e:
                _LOGGER.exception("Unexpected error during GATT read: %s", e)
                raise

    def is_connected(self):
        """Check if the device is connected."""
        return self._client.is_connected

    async def update(self):
        """Placeholder for update logic."""
        # Implement device-specific update logic here
        pass

    async def stop(self):
        """Placeholder for stopping device operations."""
        # Implement any cleanup or stopping logic here
        pass
