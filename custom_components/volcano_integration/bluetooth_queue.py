import asyncio
import logging
from bleak import BleakClient

_LOGGER = logging.getLogger(__name__)

class BluetoothQueue:
    """Queue to manage Bluetooth GATT requests."""

    def __init__(self, client: BleakClient, status_sensor):
        self.client = client
        self.queue = asyncio.Queue()
        self.connected = asyncio.Event()
        self.status_sensor = status_sensor

    async def connect(self):
        """Connect to the Bluetooth device."""
        retries = 3
        for attempt in range(1, retries + 1):
            try:
                if self.client.is_connected:
                    _LOGGER.info("Bluetooth already connected.")
                    return
                _LOGGER.info("Attempting to connect (Attempt %d/%d)...", attempt, retries)
                await self.client.connect()
                self.connected.set()
                _LOGGER.info("Bluetooth connected to %s", self.client.address)
                self.status_sensor.set_status("Connected")
                return
            except Exception as e:
                _LOGGER.error("Failed to connect: %s", e)
                await self.disconnect()
                await asyncio.sleep(2)
        _LOGGER.error("All connection attempts failed.")
        self.status_sensor.set_status("Disconnected")

    async def disconnect(self):
        """Disconnect from the Bluetooth device."""
        if not self.client.is_connected:
            _LOGGER.info("Bluetooth already disconnected.")
            return
        try:
            await self.client.disconnect()
            self.connected.clear()
            _LOGGER.info("Bluetooth disconnected.")
            self.status_sensor.set_status("Disconnected")
        except Exception as e:
            _LOGGER.error("Failed to disconnect: %s", e)

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
                _LOGGER.debug("Read UUID %s: %s", uuid, value)
                future.set_result(value)
            except Exception as e:
                _LOGGER.error("Error reading UUID %s: %s", uuid, e)
                future.set_exception(e)
            finally:
                self.queue.task_done()

    async def start(self):
        """Start processing the queue."""
        _LOGGER.info("Starting Bluetooth queue...")
        asyncio.create_task(self._process_queue())
