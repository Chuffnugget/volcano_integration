import asyncio
import logging
from bleak import BleakClient

_LOGGER = logging.getLogger(__name__)

class BluetoothQueue:
    """Queue to manage Bluetooth GATT requests."""

    def __init__(self, client: BleakClient):
        """Initialize the queue."""
        self.client = client
        self.queue = asyncio.Queue()

    async def read_gatt_char(self, uuid: str):
        """Queue a GATT read request and return the result."""
        future = asyncio.Future()
        await self.queue.put((uuid, future))
        return await future

    async def _process_queue(self):
        """Continuously process queued GATT read requests."""
        while True:
            uuid, future = await self.queue.get()
            try:
                value = await asyncio.wait_for(self.client.read_gatt_char(uuid), timeout=10)
                future.set_result(value)
                _LOGGER.debug("Successfully read UUID %s: %s", uuid, value)
            except Exception as e:
                _LOGGER.error("Error reading UUID %s: %s", uuid, e)
                future.set_exception(e)
            finally:
                self.queue.task_done()

    async def start(self):
        """Start the queue processing task."""
        asyncio.create_task(self._process_queue())
