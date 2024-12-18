"""Volcano Integration BT Device."""

from uuid import UUID
import asyncio
import logging
from contextlib import AsyncExitStack

from bleak import BleakClient
from bleak.exc import BleakError

_LOGGER = logging.getLogger(__name__)

class VolcanoBTDevice:
    """Volcano BT Device Class"""

    def __init__(self, ble_device):
        self._ble_device = ble_device
        self._client: BleakClient | None = None
        self._client_stack = AsyncExitStack()
        self._lock = asyncio.Lock()

    async def update(self):
        """Update device state."""
        # Implement any necessary update logic here
        pass

    async def stop(self):
        """Stop device operations."""
        if self._client:
            await self._client.disconnect()
            await self._client_stack.aclose()
            self._client = None

    @property
    def connected(self):
        return self._client is not None and self._client.is_connected

    async def get_client(self):
        async with self._lock:
            if not self._client:
                _LOGGER.debug("Connecting to Bluetooth device")
                try:
                    self._client = await self._client_stack.enter_async_context(BleakClient(self._ble_device, timeout=30))
                    await self._client.connect()
                except asyncio.TimeoutError as exc:
                    _LOGGER.debug("Timeout on connect", exc_info=True)
                    raise TimeoutError("Timeout on connect") from exc
                except BleakError as exc:
                    _LOGGER.debug("Error on connect", exc_info=True)
                    raise BleakError("Error on connect") from exc
            else:
                _LOGGER.debug("Connection reused")

    async def write_gatt(self, target_uuid, data):
        """Write data to a GATT characteristic."""
        await self.get_client()
        uuid = UUID(target_uuid)
        data_as_bytes = bytearray.fromhex(data)
        await self._client.write_gatt_char(uuid, data_as_bytes, response=True)

    async def read_gatt(self, target_uuid):
        """Read data from a GATT characteristic."""
        await self.get_client()
        uuid = UUID(target_uuid)
        data = await self._client.read_gatt_char(uuid)
        _LOGGER.debug(f"Read data from {uuid}: {data}")
        return data

    def update_from_advertisement(self, advertisement):
        """Update internal state from advertisement."""
        # Implement parsing logic based on advertisement data
        pass
