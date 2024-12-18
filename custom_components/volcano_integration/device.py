# device.py
"""Volcano Integration Bluetooth Device."""

from bleak import BleakClient
import asyncio
import logging

_LOGGER = logging.getLogger(__name__)

class GenericBTDevice:
    """Generic Bluetooth Device for Volcano Integration."""

    def __init__(self, ble_device):
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
                except Exception as e:
                    _LOGGER.error("Failed to connect to BLE device: %s", e)
                    raise

    async def disconnect(self):
        """Disconnect from the Bluetooth device."""
        async with self._lock:
            if self._client.is_connected:
                await self._client.disconnect()
                _LOGGER.debug("Disconnected from BLE device: %s", self._ble_device.address)

    async def write_gatt_char(self, uuid, data, response=True):
        """Write data to a GATT characteristic."""
        async with self._lock:
            await self._client.write_gatt_char(uuid, data, response=response)
            _LOGGER.debug("Wrote data to UUID %s: %s", uuid, data)

    async def read_gatt_char(self, uuid):
        """Read data from a GATT characteristic."""
        async with self._lock:
            data = await self._client.read_gatt_char(uuid)
            _LOGGER.debug("Read data from UUID %s: %s", uuid, data)
            return data

    def is_connected(self):
        """Check if the device is connected."""
        return self._client.is_connected
