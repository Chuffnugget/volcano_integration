import asyncio
import logging
from bleak import BleakClient

_LOGGER = logging.getLogger(__name__)

class BluetoothQueue:
    """Queue to manage Bluetooth GATT requests."""

    def __init__(self, client: BleakClient):
        self.client = client
        self.queue = asyncio.Queue()
        self.connected = asyncio.Event()

    async def connect(self):
        if self.client.is_connected:
            _LOGGER.info("Bluetooth already connected.")
            return
        try:
            await self.client.connect()
            self.connected.set()
            _LOGGER.info("Bluetooth connected to %s", self.client.address)
        except Exception as e:
            _LOGGER.error("Failed to connect: %s", e)
            self.connected.clear()
            raise

    async def disconnect(self):
        if not self.client.is_connected:
            _LOGGER.info("Bluetooth already disconnected.")
            return
        try:
            await self.client.disconnect()
            self.connected.clear()
            _LOGGER.info("Bluetooth disconnected from %s", self.client.address)
        except Exception as e:
            _LOGGER.error("Failed to disconnect: %s", e)
            raise

    async def read_gatt_char(self, uuid: str):
        if not self.client.is_connected:
            raise RuntimeError("Bluetooth device is not connected.")
        future = asyncio.Future()
        await self.queue.put((uuid, future))
        return await future

    async def _process_queue(self):
        while True:
            uuid, future = await self.queue.get()
            try:
                value = await asyncio.wait_for(self.client.read_gatt_char(uuid), timeout=10)
                future.set_result(value)
                _LOGGER.debug("Successfully read UUID %s: %s", uuid, value)
            except Exception as e:
                future.set_exception(e)
                _LOGGER.error("Error reading UUID %s: %s", uuid, e)
            finally:
                self.queue.task_done()

    async def start(self):
        asyncio.create_task(self._process_queue())
