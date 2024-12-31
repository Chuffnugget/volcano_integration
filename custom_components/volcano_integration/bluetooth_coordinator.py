"""Bluetooth Coordinator for the Volcano Integration, parsing separate Heat/Fan bytes from notifications."""
import asyncio
import logging

from bleak import BleakClient, BleakError

_LOGGER = logging.getLogger(__name__)

# Bluetooth Device Address
BT_DEVICE_ADDRESS = "CE:9E:A6:43:25:F3"

# GATT Characteristic UUIDs
UUID_TEMP = "10110001-5354-4f52-5a26-4249434b454c"     # Current Temperature
UUID_FAN_HEAT = "1010000c-5354-4f52-5a26-4249434b454c" # Fan/Heat (Pump) notifications

# Reconnection + Polling intervals
RECONNECT_INTERVAL = 3
POLL_INTERVAL = 0.5  # 0.5 second -> read temperature twice a second

# Possible patterns for (byte1, byte2).
# The left byte is "heat", right byte is "fan".
VALID_PATTERNS = {
    (0x23, 0x00): ("ON", "OFF"),
    (0x00, 0x00): ("OFF", "OFF"),
    (0x00, 0x30): ("OFF", "ON"),
    (0x23, 0x30): ("ON", "ON"),
}


class VolcanoBTManager:
    """
    Background loop to:
      - Connect to the BLE device
      - Poll temperature every 0.5s
      - Subscribe to fan/pump (heat/fan) notifications
      - Expose separate .heat_state and .fan_state
      - Provide .current_temperature and .bt_status
    """

    def __init__(self):
        self._client = None
        self._connected = False

        # Publicly accessible states for sensor.py
        self.current_temperature = None
        self.heat_state = None
        self.fan_state = None
        self.bt_status = "DISCONNECTED"

        self._task = None
        self._stop_event = asyncio.Event()

        # Keep track of sensors that want immediate updates
        self._sensors = []

    def register_sensor(self, sensor_entity):
        """Allow a sensor entity to register for immediate notifications."""
        if sensor_entity not in self._sensors:
            self._sensors.append(sensor_entity)

    def unregister_sensor(self, sensor_entity):
        """Remove a sensor from the update list."""
        if sensor_entity in self._sensors:
            self._sensors.remove(sensor_entity)

    def start(self, hass):
        """
        Start the background loop in Home Assistant’s event loop.
        We'll attempt to connect, read temperature every 0.5s,
        and subscribe for fan/pump notifications.
        """
        _LOGGER.debug("VolcanoBTManager.start() -> creating background task.")
        self._stop_event.clear()
        self._task = hass.loop.create_task(self._run())

    def stop(self):
        """Stop the background loop by signaling the event."""
        _LOGGER.debug("VolcanoBTManager.stop() -> stopping background task.")
        if self._task and not self._task.done():
            self._stop_event.set()

    async def _run(self):
        """Main loop: connect if needed, read temp every 0.5s, handle reconnect."""
        _LOGGER.debug("Entering VolcanoBTManager._run() loop.")
        while not self._stop_event.is_set():
            if not self._connected:
                await self._connect()

            if self._connected:
                # Poll temperature
                await self._read_temperature()

            await asyncio.sleep(POLL_INTERVAL)

        _LOGGER.debug("Exiting VolcanoBTManager._run() loop -> disconnecting.")
        await self._disconnect()

    async def _connect(self):
        """Attempt to connect to the BLE device."""
        try:
            _LOGGER.info("Connecting to Bluetooth device %s...", BT_DEVICE_ADDRESS)
            self.bt_status = "CONNECTING"

            self._client = BleakClient(BT_DEVICE_ADDRESS)
            await self._client.connect()

            # is_connected is a property in newer Bleak
            self._connected = self._client.is_connected

            if self._connected:
                _LOGGER.info("Bluetooth connected to %s", BT_DEVICE_ADDRESS)
                self.bt_status = "CONNECTED"
                # Subscribe for fan/pump notifications
                await self._subscribe_notifications()
            else:
                _LOGGER.warning("Connection to %s unsuccessful. Retrying in %s sec.",
                                BT_DEVICE_ADDRESS, RECONNECT_INTERVAL)
                self.bt_status = "DISCONNECTED"
                await asyncio.sleep(RECONNECT_INTERVAL)

        except BleakError as e:
            err_str = f"ERROR: {e}"
            _LOGGER.error("Bluetooth connect error: %s -> Retrying in %s sec.",
                          err_str, RECONNECT_INTERVAL)
            self.bt_status = err_str
            await asyncio.sleep(RECONNECT_INTERVAL)

    async def _subscribe_notifications(self):
        """Subscribe to fan/pump (heat/fan) notifications."""
        if not self._connected or not self._client:
            _LOGGER.error("Cannot subscribe to fan/pump notifications: not connected.")
            return

        def notification_handler(sender: int, data: bytearray):
            """
            Called whenever the device pushes data on the Fan/Heat (Pump) UUID.
            The left byte is heat, right byte is fan. We parse it via VALID_PATTERNS.
            """
            _LOGGER.debug("Fan/Pump notification raw: %s (hex)", data.hex())
            b1, b2 = 0, 0
            if len(data) >= 2:
                b1, b2 = data[0], data[1]

            if (b1, b2) in VALID_PATTERNS:
                heat_val, fan_val = VALID_PATTERNS[(b1, b2)]
                self.heat_state = heat_val
                self.fan_state = fan_val
                _LOGGER.debug(
                    "Parsed fan/pump => heat=%s, fan=%s (pattern=(0x%02x, 0x%02x))",
                    heat_val, fan_val, b1, b2
                )
            else:
                self.heat_state = "UNKNOWN"
                self.fan_state = "UNKNOWN"
                _LOGGER.warning(
                    "Received unknown fan/pump pattern: (0x%02x, 0x%02x). Defaulting to UNKNOWN.",
                    b1, b2
                )

            # Notify sensors so they update in HA
            self._notify_sensors()

        try:
            _LOGGER.info("Subscribing to fan/pump notifications on UUID %s", UUID_FAN_HEAT)
            await self._client.start_notify(UUID_FAN_HEAT, notification_handler)
            _LOGGER.debug("Fan/pump subscription active.")
        except BleakError as e:
            err_str = f"ERROR subscribing to fan/pump: {e}"
            _LOGGER.error(err_str)
            self.bt_status = err_str

    async def _read_temperature(self):
        """Read the temperature characteristic every 0.5 seconds."""
        if not self._connected or not self._client:
            _LOGGER.debug("Not connected -> skipping temperature read.")
            return

        try:
            data = await self._client.read_gatt_char(UUID_TEMP)
            _LOGGER.debug("Read temperature raw bytes: %s", data.hex())

            if len(data) < 2:
                _LOGGER.warning("Temperature data too short: %d bytes", len(data))
                self.current_temperature = None
            else:
                raw_16 = int.from_bytes(data[:2], byteorder="little", signed=False)
                self.current_temperature = raw_16 / 10.0
                _LOGGER.debug("Parsed temperature = %.1f °C (raw=%d)",
                              self.current_temperature, raw_16)

            # Notify sensors so they can push an immediate update
            self._notify_sensors()

        except BleakError as e:
            _LOGGER.error("Error reading temperature: %s -> disconnect & retry.", e)
            self.bt_status = f"ERROR: {e}"
            await self._disconnect()

    def _notify_sensors(self):
        """Informs any registered sensors that new data is available."""
        for sensor_entity in self._sensors:
            sensor_entity.schedule_update_ha_state(True)

    async def _disconnect(self):
        """Disconnect from the device so we can attempt to reconnect next cycle."""
        if self._client:
            _LOGGER.debug("Disconnecting from device %s.", BT_DEVICE_ADDRESS)
            try:
                await self._client.disconnect()
            except BleakError as e:
                _LOGGER.error("Error during disconnect: %s", e)

        self._client = None
        self._connected = False
        self.bt_status = "DISCONNECTED"
        _LOGGER.info("Disconnected from device %s. Will retry later.", BT_DEVICE_ADDRESS)
