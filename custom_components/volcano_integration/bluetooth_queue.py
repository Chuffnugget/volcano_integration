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
        self.connected = asyncio.Event()  # Event to track connection state

    async def connect(self):
        """Connect to the Bluetooth device."""
        if self.client.is_connected:
            _LOGGER.info("Bluetooth already connected.")
            return

        try:
            await self.client.connect()
            self.connected.set()
            _LOGGER.info("Bluetooth connected to %s", self.client.address)
        except Exception as e:
            _LOGGER.error("Failed to connect to Bluetooth device: %s", e)
            self.connected.clear()
            raise

    async def disconnect(self):
        """Disconnect from the Bluetooth device."""
        if not self.client.is_connected:
            _LOGGER.info("Bluetooth already disconnected.")
            return

        try:
            await self.client.disconnect()
            self.connected.clear()
            _LOGGER.info("Bluetooth disconnected from %s", self.client.address)
        except Exception as e:
            _LOGGER.error("Failed to disconnect from Bluetooth device: %s", e)
            raise

    async def read_gatt_char(self, uuid: str):
        """Queue a GATT read request and return the result."""
        if not self.client.is_connected:
            raise RuntimeError("Bluetooth device is not connected.")

        future = asyncio.Future()
        await self.queue.put((uuid, future))
        return await future

    async def _process_queue(self):
        """Continuously process queued GATT read requests."""
        while True:
            uuid, future = await self.queue.get()
            try:
                value = await asyncio.wait_for(self.client.read_gatt_char(uuid), timeout=10)
                _LOGGER.debug("Successfully read UUID %s: %s", uuid, value)
                future.set_result(value)
            except Exception as e:
                _LOGGER.error("Error reading UUID %s: %s", uuid, e)
                future.set_exception(e)
            finally:
                self.queue.task_done()

    async def start(self):
        """Start processing the queue."""
        asyncio.create_task(self._process_queue())
