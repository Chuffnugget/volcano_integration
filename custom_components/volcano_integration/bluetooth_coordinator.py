"""Bluetooth Coordinator for the Volcano Integration with improved RSSI on HA OS + GATT writes support."""
import asyncio
import logging
import time

from bleak import BleakClient, BleakError

_LOGGER = logging.getLogger(__name__)

BT_DEVICE_ADDRESS = "CE:9E:A6:43:25:F3"

# GATT Characteristic UUIDs
UUID_TEMP = "10110001-5354-4f52-5a26-4249434b454c"      # Current Temperature
UUID_FAN_HEAT = "1010000c-5354-4f52-5a26-4249434b454c"  # Fan/Pump notifications

# Pump/Heat Write UUIDs
UUID_PUMP_ON  = "10110013-5354-4f52-5a26-4249434b454c"
UUID_PUMP_OFF = "10110014-5354-4f52-5a26-4249434b454c"
UUID_HEAT_ON  = "1011000f-5354-4f52-5a26-4249434b454c"
UUID_HEAT_OFF = "10110010-5354-4f52-5a26-4249434b454c"

# Timings
RECONNECT_INTERVAL = 3      # 3s before reconnect attempts
POLL_INTERVAL = 0.5         # 0.5s for temperature
RSSI_INTERVAL = 60.0        # 60s for RSSI

VALID_PATTERNS = {
    (0x23, 0x00): ("ON", "OFF"),
    (0x00, 0x00): ("OFF", "OFF"),
    (0x00, 0x30): ("OFF", "ON"),
    (0x23, 0x30): ("ON", "ON"),
}


class VolcanoBTManager:
    """
    Manages:
      - A background loop that polls temperature every 0.5s
      - Subscribes to fan/pump notifications
      - Reads RSSI every 60s (if supported by the backend)
      - Exposes write_gatt_command() for Pump/Heat ON/OFF
      - Provides user connect/disconnect methods
      - Reverted _connect() approach using 'await is_connected()'
      - Calls get_services() after connect, which often helps finalize RSSI support on HA OS
    """

    def __init__(self):
        self._hass = None
        self._client = None
        self._connected = False

        self.current_temperature = None
        self.heat_state = None
        self.fan_state = None
        self.rssi = None

        self.bt_status = "DISCONNECTED"

        self._task = None
        self._stop_event = asyncio.Event()
        self._sensors = []

        # Track last time we read RSSI
        self._last_rssi_time = 0.0

    def register_sensor(self, sensor_entity):
        """Register a sensor so it can be notified of new data."""
        if sensor_entity not in self._sensors:
            self._sensors.append(sensor_entity)

    def unregister_sensor(self, sensor_entity):
        """Unregister a sensor."""
        if sensor_entity in self._sensors:
            self._sensors.remove(sensor_entity)

    def start(self, hass):
        """Start the manager in Home Assistant's event loop."""
        _LOGGER.debug("VolcanoBTManager.start() -> creating background task.")
        self._hass = hass
        self._stop_event.clear()
        self._task = hass.loop.create_task(self._run())

    def stop(self):
        """Stop the background loop by setting the stop_event."""
        _LOGGER.debug("VolcanoBTManager.stop() -> stopping background task.")
        if self._task and not self._task.done():
            self._stop_event.set()

    async def _run(self):
        """Main loop: connect if needed, poll temperature, handle RSSI, etc."""
        _LOGGER.debug("Entering VolcanoBTManager._run() loop.")
        while not self._stop_event.is_set():
            if not self._connected:
                await self._connect()

            if self._connected:
                # Poll temperature
                await self._read_temperature()

                # Periodically read RSSI
                now = time.time()
                if (now - self._last_rssi_time) >= RSSI_INTERVAL:
                    await self._read_rssi()
                    self._last_rssi_time = now

            await asyncio.sleep(POLL_INTERVAL)

        _LOGGER.debug("Exiting VolcanoBTManager._run() -> disconnecting.")
        await self._disconnect()

    async def _connect(self):
        """Attempt to connect to the BLE device (old approach: await is_connected())."""
        try:
            _LOGGER.info("Connecting to Bluetooth device %s...", BT_DEVICE_ADDRESS)
            self.bt_status = "CONNECTING"

            self._client = BleakClient(BT_DEVICE_ADDRESS)

            await self._client.connect()
            # Often helps finalize discovery on Linux/BlueZ
            await self._client.get_services()

            self._connected = await self._client.is_connected()

            if self._connected:
                _LOGGER.info("Bluetooth connected to %s", BT_DEVICE_ADDRESS)
                self.bt_status = "CONNECTED"
                await self._subscribe_notifications()
            else:
                _LOGGER.warning(
                    "Connection to %s unsuccessful. Retrying in %s sec...",
                    BT_DEVICE_ADDRESS, RECONNECT_INTERVAL
                )
                self.bt_status = "DISCONNECTED"
                await asyncio.sleep(RECONNECT_INTERVAL)

        except BleakError as e:
            err_str = f"ERROR: {e}"
            _LOGGER.error(
                "Bluetooth connect error: %s -> Retrying in %s sec...",
                err_str, RECONNECT_INTERVAL
            )
            self.bt_status = err_str
            await asyncio.sleep(RECONNECT_INTERVAL)

    async def _subscribe_notifications(self):
        """Subscribe to fan/pump notifications (two-byte pattern)."""
        if not self._connected or not self._client:
            _LOGGER.error("Cannot subscribe to fan/pump notifications: not connected.")
            return

        def notification_handler(sender: int, data: bytearray):
            _LOGGER.debug("Fan/Pump notification raw: %s", data.hex())
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
                        "Unknown fan/pump pattern (0x%02x, 0x%02x).", b1, b2
                    )
            else:
                self.heat_state = "UNKNOWN"
                self.fan_state = "UNKNOWN"
                _LOGGER.warning("Fan/Pump notification too short: %d byte(s).", len(data))

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
        """Read the temperature characteristic every 0.5s."""
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
                _LOGGER.debug(
                    "Parsed temperature = %.1f °C (raw=%d)",
                    self.current_temperature, raw_16
                )

            self._notify_sensors()

        except BleakError as e:
            _LOGGER.error("Error reading temperature: %s -> disconnect & retry...", e)
            self.bt_status = f"ERROR: {e}"
            await self._disconnect()

    async def _read_rssi(self):
        """Read the RSSI (dBm) every 60s, if supported by the backend."""
        if not self._connected or not self._client:
            _LOGGER.debug("Not connected -> skipping RSSI read.")
            return

        try:
            rssi_val = await self._client.get_rssi()
        except (AttributeError, NotImplementedError) as e_attr:
            _LOGGER.debug("get_rssi() not implemented on this backend: %s", e_attr)
            rssi_val = None
        except BleakError as e:
            _LOGGER.error("BleakError while reading RSSI: %s", e)
            rssi_val = None

        if rssi_val is not None:
            _LOGGER.debug("Read RSSI = %s dBm", rssi_val)
            self.rssi = rssi_val
        else:
            self.rssi = None
            _LOGGER.debug("RSSI not supported or returned None.")

        self._notify_sensors()

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

    # -------------------------------------------------------------------------
    # Write GATT Command: Pump/Heat ON/OFF
    # -------------------------------------------------------------------------
    async def write_gatt_command(self, write_uuid: str):
        """
        Called by our button entities to write a GATT characteristic for
        Pump ON/OFF or Heat ON/OFF.
        """
        if not self._connected or not self._client:
            _LOGGER.warning("Cannot write to %s - not connected.", write_uuid)
            return

        try:
            # We'll write an empty payload, assuming the characteristic triggers ON/OFF
            _LOGGER.debug("Writing GATT char %s -> empty payload", write_uuid)
            await self._client.write_gatt_char(write_uuid, b"")  # or b"\x01" if needed
            _LOGGER.info("Successfully wrote to %s", write_uuid)
        except BleakError as e:
            _LOGGER.error("Error writing to %s: %s", write_uuid, e)
            self.bt_status = f"ERROR: {e}"
            self._notify_sensors()

    # -------------------------------------------------------------------------
    # Connect/Disconnect button methods
    # -------------------------------------------------------------------------
    async def async_user_connect(self):
        """
        Called when user presses 'Connect' button:
          - Stop any running loop
          - Re-start the background _run() loop
        """
        _LOGGER.debug("User pressed Connect button -> re-connecting BLE.")
        self.stop()
        if self._task and not self._task.done():
            _LOGGER.debug("Waiting for old task to finish before reconnect.")
            await self._task

        self._stop_event.clear()
        self._task = self._hass.loop.create_task(self._run())

    async def async_user_disconnect(self):
        """
        Called when user presses 'Disconnect' button:
          - Stop the loop
          - Fully disconnect
          - Mark status as DISCONNECTED
        """
        _LOGGER.debug("User pressed Disconnect button -> stopping BLE.")
        self.stop()
        if self._task and not self._task.done():
            _LOGGER.debug("Waiting for old task to exit.")
            await self._task

        await self._disconnect()
        self.bt_status = "DISCONNECTED"
        _LOGGER.debug("Set bt_status to DISCONNECTED after user request.")
        self._notify_sensors()
