"""Bluetooth Coordinator for the Volcano Integration."""

import asyncio
import logging
from bleak import BleakClient, BleakError

_LOGGER = logging.getLogger(__name__)

# Replace with your device's MAC address
BT_DEVICE_ADDRESS = "CE:9E:A6:43:25:F3"

# Timings
RECONNECT_INTERVAL = 3  # Seconds before attempting to reconnect
TEMP_POLL_INTERVAL = 1  # Seconds between temperature polls

# Pump patterns: (heat_byte, pump_byte)
VALID_PATTERNS = {
    (0x23, 0x00): ("ON", "OFF"),
    (0x00, 0x00): ("OFF", "OFF"),
    (0x00, 0x30): ("OFF", "ON"),
    (0x23, 0x30): ("ON", "ON"),
    (0x23, 0x06): ("BURST_STARTED", "ON"),  # Start of burst
    (0x23, 0x26): ("BURST_ENDED", "ON"),    # End of burst
}


class VolcanoBTManager:
    """Manages Bluetooth communication with the Volcano device."""

    def __init__(self):
        self._client = None
        self._connected = False
        self.current_temperature = None
        self.heat_state = None
        self.pump_state = None
        self.bt_status = "DISCONNECTED"
        self._run_task = None
        self._temp_poll_task = None
        self._stop_event = asyncio.Event()
        self._sensors = []

        # Define UUIDs
        self.UUID_TEMP = "10110001-5354-4f52-5a26-4249434b454c"
        self.UUID_PUMP_NOTIFICATIONS = "1010000c-5354-4f52-5a26-4249434b454c"
        self.UUID_PUMP_ON = "10110013-5354-4f52-5a26-4249434b454c"
        self.UUID_PUMP_OFF = "10110014-5354-4f52-5a26-4249434b454c"
        self.UUID_HEAT_ON = "1011000f-5354-4f52-5a26-4249434b454c"
        self.UUID_HEAT_OFF = "10110010-5354-4f52-5a26-4249434b454c"
        self.UUID_HEATER_SETPOINT = "10110003-5354-4f52-5a26-4249434b454c"

    def register_sensor(self, sensor_entity):
        """Register a sensor to receive updates."""
        if sensor_entity not in self._sensors:
            self._sensors.append(sensor_entity)

    def unregister_sensor(self, sensor_entity):
        """Unregister a sensor from receiving updates."""
        if sensor_entity in self._sensors:
            self._sensors.remove(sensor_entity)

    async def start(self):
        """Start the Bluetooth manager."""
        if not self._run_task or self._run_task.done():
            self._stop_event.clear()
            self._run_task = asyncio.create_task(self._run())
            self._temp_poll_task = asyncio.create_task(self._poll_temperature())

    async def stop(self):
        """Stop the Bluetooth manager."""
        if self._run_task and not self._run_task.done():
            self._stop_event.set()
            await self._run_task
        if self._temp_poll_task and not self._temp_poll_task.done():
            self._temp_poll_task.cancel()
            try:
                await self._temp_poll_task
            except asyncio.CancelledError:
                pass

    async def _run(self):
        """Main loop to manage Bluetooth connection."""
        _LOGGER.debug("Entering VolcanoBTManager._run() loop.")
        while not self._stop_event.is_set():
            if not self._connected:
                await self._connect()
            await asyncio.sleep(1)

        _LOGGER.debug("Exiting VolcanoBTManager._run() -> disconnecting.")
        await self._disconnect()

    async def _connect(self):
        """Attempt to connect to the BLE device."""
        try:
            _LOGGER.info("Connecting to Bluetooth device %s...", BT_DEVICE_ADDRESS)
            self.bt_status = "CONNECTING"
            self._client = BleakClient(BT_DEVICE_ADDRESS)
            await self._client.connect()

            # Ensure discovery of services
            _LOGGER.debug("Services discovered: %s", self._client.services)
            self._connected = self._client.is_connected

            if self._connected:
                _LOGGER.info("Bluetooth connected to %s", BT_DEVICE_ADDRESS)
                self.bt_status = "CONNECTED"
                await self._subscribe_pump_notifications()
            else:
                self.bt_status = "DISCONNECTED"
                await asyncio.sleep(RECONNECT_INTERVAL)

        except BleakError as e:
            _LOGGER.error("Bluetooth connect error: %s -> Retrying...", e)
            self.bt_status = "ERROR"
            await asyncio.sleep(RECONNECT_INTERVAL)

    async def _subscribe_pump_notifications(self):
        """Subscribe to pump notifications."""
        if not self._connected:
            _LOGGER.error("Cannot subscribe to pump notifications: not connected.")
            return

        async def notification_handler(sender, data):
            """Handle incoming notifications."""
            _LOGGER.debug("Pump notification raw: %s", data.hex())
            if len(data) >= 2:
                b1, b2 = data[0], data[1]
                _LOGGER.debug("Received bytes: 0x%02x, 0x%02x", b1, b2)
                if (b1, b2) in VALID_PATTERNS:
                    heat_val, pump_val = VALID_PATTERNS[(b1, b2)]
                    self.heat_state = heat_val
                    self.pump_state = pump_val
                    _LOGGER.info("Parsed notification -> heat=%s, pump=%s", heat_val, pump_val)
                    if (b1, b2) == (0x23, 0x06):
                        _LOGGER.info("Burst of air started at %.1f°C", self.current_temperature or -1)
                    elif (b1, b2) == (0x23, 0x26):
                        _LOGGER.info("Burst of air ended at %.1f°C", self.current_temperature or -1)
                else:
                    self.heat_state = "UNKNOWN"
                    self.pump_state = "UNKNOWN"
                    _LOGGER.warning("Unknown pump pattern received: 0x%02x, 0x%02x", b1, b2)
            else:
                self.heat_state = "UNKNOWN"
                self.pump_state = "UNKNOWN"
                _LOGGER.warning("Pump notification too short: %d byte(s).", len(data))

            self._notify_sensors()

        try:
            await self._client.start_notify(self.UUID_PUMP_NOTIFICATIONS, notification_handler)
        except BleakError as e:
            _LOGGER.error("Error subscribing to notifications: %s", e)

    async def _poll_temperature(self):
        """Poll temperature at regular intervals."""
        while not self._stop_event.is_set():
            if self._connected:
                await self._read_temperature()
            await asyncio.sleep(TEMP_POLL_INTERVAL)

    async def _read_temperature(self):
        """Read the temperature characteristic."""
        if not self._connected or not self._client:
            _LOGGER.debug("Not connected -> skipping temperature read.")
            return

        try:
            data = await self._client.read_gatt_char(self.UUID_TEMP)
            _LOGGER.debug("Read temperature raw bytes: %s", data.hex())

            if len(data) < 2:
                _LOGGER.warning("Temperature data too short: %d bytes", len(data))
                self.current_temperature = None
            else:
                raw_16 = int.from_bytes(data[:2], byteorder="little", signed=False)
                self.current_temperature = raw_16 / 10.0
                _LOGGER.debug("Parsed temperature = %.1f °C (raw=%d)", self.current_temperature, raw_16)

            self._notify_sensors()

        except BleakError as e:
            _LOGGER.error("Error reading temperature: %s -> disconnect & retry...", e)
            self.bt_status = f"ERROR: {e}"
            await self._disconnect()

    def _notify_sensors(self):
        """Notify all registered sensors that new data is available."""
        for sensor_entity in self._sensors:
            sensor_entity.schedule_update_ha_state(True)

    async def _disconnect(self):
        """Disconnect from the BLE device so we can attempt to reconnect next cycle."""
        if self._client:
            _LOGGER.debug("Disconnecting from device %s.", BT_DEVICE_ADDRESS)
            try:
                await self._client.disconnect()
            except BleakError as e:
                _LOGGER.error("Error during disconnect: %s", e)

        self._client = None
        self._connected = False
        self.bt_status = "DISCONNECTED"
        _LOGGER.info("Disconnected from device %s.", BT_DEVICE_ADDRESS)

    async def write_gatt_command(self, write_uuid: str, payload: bytes = b""):
        """Write a payload to a GATT characteristic to control Pump/Heat."""
        if not self._connected or not self._client:
            _LOGGER.warning("Cannot write to %s - not connected.", write_uuid)
            return

        try:
            _LOGGER.debug("Writing GATT char %s -> payload %s", write_uuid, payload.hex())
            await self._client.write_gatt_char(write_uuid, payload)
            _LOGGER.info("Successfully wrote to %s", write_uuid)
        except BleakError as e:
            _LOGGER.error("Error writing to %s: %s", write_uuid, e)

    async def set_heater_temperature(self, temp_c: float):
        """Write the temperature setpoint to the heater's GATT characteristic."""
        if not self._connected or not self._client:
            _LOGGER.warning("Cannot set heater temperature - not connected.")
            return

        safe_temp = max(40.0, min(temp_c, 230.0))
        setpoint_int = int(safe_temp * 10)
        setpoint_bytes = setpoint_int.to_bytes(2, byteorder="little", signed=False)

        _LOGGER.debug("Writing heater temperature=%.1f °C -> raw=%s", safe_temp, setpoint_bytes.hex())
        try:
            await self._client.write_gatt_char(self.UUID_HEATER_SETPOINT, setpoint_bytes)
            _LOGGER.info("Heater setpoint updated to %.1f °C", safe_temp)
        except BleakError as e:
            _LOGGER.error("Error writing heater temp: %s", e)
