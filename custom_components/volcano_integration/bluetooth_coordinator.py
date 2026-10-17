"""Own the Volcano connection, serialized I/O and shared device state."""

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace
from typing import Any

from bleak import BleakClient, BleakError
from bleak.exc import BleakCharacteristicNotFoundError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import persistent_notification
from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

from .const import (
    BT_STATUS_CONNECTED,
    BT_STATUS_CONNECTING,
    BT_STATUS_DISCONNECTED,
    CONNECT_WAIT_TIMEOUT,
    DOMAIN,
    IO_TIMEOUT,
    MAX_BRIGHTNESS,
    MAX_RECONNECT_INTERVAL,
    MAX_SHUTOFF_MINUTES,
    MIN_BRIGHTNESS,
    MIN_SHUTOFF_MINUTES,
    RECONNECT_INTERVAL,
    REGISTER2_UUID,
    REGISTER3_UUID,
    SETTINGS_POLL_INTERVAL,
    TEMP_POLL_INTERVAL,
    TEMPERATURE_TIMEOUT,
    UUID_AUTO_SHUT_OFF_SETTING,
    UUID_BLE_FIRMWARE_VERSION,
    UUID_FIRMWARE_VERSION,
    UUID_HEAT_OFF,
    UUID_HEAT_ON,
    UUID_HEATER_SETPOINT,
    UUID_HOURS_OF_OPERATION,
    UUID_LED_BRIGHTNESS,
    UUID_MINUTES_OF_OPERATION,
    UUID_PUMP_NOTIFICATIONS,
    UUID_PUMP_OFF,
    UUID_PUMP_ON,
    UUID_SERIAL_NUMBER,
    UUID_TEMP,
)
from .models import VolcanoState
from .protocol import (
    ProtocolError,
    decode_brightness,
    decode_status,
    decode_temperature,
    decode_temperature_unit,
    decode_text,
    decode_uint,
    decode_vibration,
    encode_temperature,
    encode_temperature_unit,
    encode_vibration,
)

_LOGGER = logging.getLogger(__name__)
CONNECTION_ERRORS = (BleakError, TimeoutError, OSError, EOFError, ProtocolError)
METADATA_READS = (
    (UUID_BLE_FIRMWARE_VERSION, "ble_firmware_version", decode_text),
    (UUID_SERIAL_NUMBER, "serial_number", decode_text),
    (UUID_FIRMWARE_VERSION, "firmware_version", decode_text),
)
SETTINGS_READS = (
    (UUID_LED_BRIGHTNESS, "led_brightness", decode_brightness),
    (UUID_AUTO_SHUT_OFF_SETTING, "auto_shut_off_setting", lambda data: decode_uint(data) // 60),
    (UUID_HOURS_OF_OPERATION, "hours_of_operation", decode_uint),
    (UUID_MINUTES_OF_OPERATION, "minutes_of_operation", decode_uint),
    (REGISTER3_UUID, "vibration", decode_vibration),
)


class VolcanoBTManager:
    """A user-controlled persistent connection with one cancellable worker."""

    def __init__(self, hass: HomeAssistant, bt_address: str, *, config_entry_id: str) -> None:
        self.hass = hass
        self.bt_address = bt_address
        self._config_entry_id = config_entry_id
        self.state = VolcanoState()
        self._client: BleakClientWithServiceCache | None = None
        self._use_services_cache = True
        self._run_task: asyncio.Task | None = None
        self._requested = False
        self._closed = False
        self._lifecycle_lock = asyncio.Lock()
        self._io_lock = asyncio.Lock()
        self._disconnected = asyncio.Event()
        self._retry_now = asyncio.Event()
        self._changed = asyncio.Event()
        self._listeners: set[Callable[[], None]] = set()
        self._generation = 0
        self._status_sequence = 0
        self._status_received = False
        self._unit_write_acknowledged = False
        self._outputs_notified_off = False
        self._unit_notification_received = False
        self._unit_sequence = 0
        self._temperature_sequence = 0
        self._temperature_read_at: float | None = None

    @property
    def connected(self) -> bool:
        """Ready means initialization and subscriptions have completed."""
        return (
            self._requested
            and not self._closed
            and self.state.bt_status == BT_STATUS_CONNECTED
            and self._client is not None
            and self._client.is_connected
            and not self._disconnected.is_set()
        )

    @property
    def connection_requested(self) -> bool:
        return self._requested

    @property
    def supports_temperature_unit(self) -> bool:
        """Whether this connection can report the physical display unit."""
        if self._client is None:
            return False
        characteristic = self._client.services.get_characteristic(REGISTER2_UUID)
        return characteristic is not None and bool(
            {"read", "notify"}.intersection(characteristic.properties)
        )

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Subscribe without retaining Home Assistant entity objects."""
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    @callback
    def _publish(self, **changes: Any) -> None:
        # Intent can change while status stays DISCONNECTED during retry backoff.
        changes["connection_requested"] = self._requested
        updated = replace(self.state, **changes)
        changed = updated != self.state
        self.state = updated
        # Wake waiters even when two consecutive temperature samples are equal.
        previous_event, self._changed = self._changed, asyncio.Event()
        previous_event.set()
        if changed:
            for listener in tuple(self._listeners):
                try:
                    listener()
                except Exception:
                    # One entity must not stop polling or other entity updates.
                    _LOGGER.exception("Error updating a Volcano entity")

    @callback
    def _invalidate(self) -> None:
        """Never let readings from an old connection satisfy a workflow wait."""
        self._temperature_read_at = None
        self._status_received = False
        self._unit_write_acknowledged = False
        self._outputs_notified_off = False
        self._unit_notification_received = False
        self._publish(
            bt_status=BT_STATUS_DISCONNECTED,
            current_temperature=None,
            target_temperature=None,
            temperature_unit=None,
            temperature_unit_fallback=None,
            heat_state=None,
            pump_state=None,
            raw_status=None,
            auto_shut_off_setting=None,
            led_brightness=None,
            hours_of_operation=None,
            minutes_of_operation=None,
            vibration=None,
        )

    async def async_user_connect(self) -> None:
        """Start one worker, or wake an existing worker from backoff."""
        async with self._lifecycle_lock:
            if self._closed:
                raise HomeAssistantError("Volcano integration is unloaded or shutting down")
            self._requested = True
            self._publish()
            if self._run_task is None or self._run_task.done():
                self._run_task = self.hass.async_create_background_task(
                    self._run(), f"volcano {self.bt_address}"
                )
            else:
                self._retry_now.set()

    async def async_user_disconnect(self) -> None:
        """Turn off both outputs before disconnecting, or cancel a pending connection."""
        async with self._lifecycle_lock:
            shutdown_confirmed = True
            if self.connected:
                try:
                    async with self._io_lock:
                        if not self.connected:
                            raise HomeAssistantError("Volcano is no longer connected")
                        shutdown_confirmed = await self._turn_off_outputs()
                        # Reject commands already queued behind these off writes before
                        # releasing the I/O lock and cancelling the connection worker.
                        self._requested = False
                except (HomeAssistantError, *CONNECTION_ERRORS) as err:
                    if self.connected:
                        detail = "Bluetooth is still connected. Check the Volcano and retry."
                    else:
                        await self._stop_locked()
                        detail = "Bluetooth was lost. Check heat and air on the Volcano itself."
                    raise HomeAssistantError(f"{err}. {detail}") from err
            await self._stop_locked()
            if not shutdown_confirmed:
                message = (
                    "Both OFF commands were acknowledged, but this Volcano did not report "
                    "its heat or air status. Bluetooth has been disconnected. "
                    "Check that heat and air are off on the device."
                )
                _LOGGER.warning("Volcano %s: %s", self.bt_address, message)
                persistent_notification.async_create(
                    self.hass,
                    message,
                    title="Volcano: check heat and air",
                    notification_id=f"{DOMAIN}_{self._config_entry_id}_shutdown_unconfirmed",
                )

    async def _turn_off_outputs(self) -> bool:
        """Turn both outputs off; return whether their status confirmed shutdown."""
        confirmation_sequence = self._status_sequence
        already_off = (
            self._outputs_notified_off
            and self.state.heat_state is False
            and self.state.pump_state is False
        )
        errors = []
        acknowledgements = []
        for name, uuid in (("heat", UUID_HEAT_OFF), ("air", UUID_PUMP_OFF)):
            try:
                acknowledgements.append(await self._write(uuid, b"\x00"))
            except (HomeAssistantError, *CONNECTION_ERRORS) as err:
                errors.append(f"{name}: {err}")
        if errors:
            raise HomeAssistantError(f"Could not turn off {'; '.join(errors)}")

        try:
            async with asyncio.timeout(IO_TIMEOUT):
                while True:
                    changed = self._changed
                    sequence = self._status_sequence
                    data = await self._read_optional(UUID_PUMP_NOTIFICATIONS)
                    if data is not None and sequence == self._status_sequence:
                        self._update_status(data)
                    if not self.connected:
                        raise HomeAssistantError("Volcano disconnected before confirming shutdown")
                    fresh_status = data is not None or self._status_sequence > confirmation_sequence
                    if (
                        fresh_status
                        and self.state.heat_state is False
                        and self.state.pump_state is False
                    ):
                        return True
                    if data is None:
                        characteristic = self._client.services.get_characteristic(
                            UUID_PUMP_NOTIFICATIONS
                        )
                        if characteristic is None or "notify" not in characteristic.properties:
                            raise HomeAssistantError("Heat and air status is unavailable")
                        # Notify-only firmware may send nothing when already off.
                        # Only trust an off notification from this connection, with no
                        # intervening ON command or contradictory status.
                        if (
                            already_off
                            and self._outputs_notified_off
                            and self.state.heat_state is False
                            and self.state.pump_state is False
                        ):
                            return True
                        # Notifications run without the I/O lock. Keep queued commands
                        # blocked until a fresh status confirms both outputs are off.
                        await changed.wait()
                    else:
                        await asyncio.sleep(0.1)
        except TimeoutError as err:
            if self.connected and not self._status_received and all(acknowledgements):
                characteristic = self._client.services.get_characteristic(UUID_PUMP_NOTIFICATIONS)
                if (
                    characteristic is not None
                    and "notify" in characteristic.properties
                    and "read" not in characteristic.properties
                ):
                    # An idle notify-only device may never send its first status.
                    # Both acknowledged OFF writes are required for this fallback.
                    return False
            raise HomeAssistantError("Volcano did not confirm that heat and air are off") from err

    async def async_shutdown(self) -> None:
        """Permanently close this entry's manager before waiting for its worker."""
        self._closed = True
        await self.stop()

    async def stop(self) -> None:
        """Cancel in-flight connects, polling and backoff, then release BLE."""
        async with self._lifecycle_lock:
            await self._stop_locked()

    async def _stop_locked(self) -> None:
        """Release the worker while the caller holds the lifecycle lock."""
        self._requested = False
        self._publish()
        if self._run_task is not None:
            self._run_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._run_task
            self._run_task = None
        self._invalidate()

    async def _run(self) -> None:
        delay = RECONNECT_INTERVAL
        try:
            while self._requested:
                self._disconnected.clear()
                self._retry_now.clear()
                try:
                    await self._connect()
                    delay = RECONNECT_INTERVAL
                    polls = 0
                    loop = asyncio.get_running_loop()
                    next_settings_read = loop.time() + SETTINGS_POLL_INTERVAL
                    while self._requested and self.connected:
                        async with self._io_lock:
                            await self._read_temperature()
                            # Observe changes made on the physical device too.
                            if polls % 5 == 0:
                                await self._read_setpoint()
                                await self._read_temperature_unit()
                            if loop.time() >= next_settings_read:
                                await self._read_fields(SETTINGS_READS)
                                next_settings_read = loop.time() + SETTINGS_POLL_INTERVAL
                        polls += 1
                        with suppress(TimeoutError):
                            await asyncio.wait_for(self._disconnected.wait(), TEMP_POLL_INTERVAL)
                except BleakCharacteristicNotFoundError as err:
                    _LOGGER.debug(
                        "Volcano %s has incomplete Bluetooth services: %s", self.bt_address, err
                    )
                    async with self._io_lock:
                        await self._clear_service_cache()
                except CONNECTION_ERRORS as err:
                    _LOGGER.debug("Volcano %s unavailable: %s", self.bt_address, err)
                finally:
                    # Cancellation during disconnect must still release the BLE slot.
                    cleanup = asyncio.create_task(self._disconnect())
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        await cleanup
                        raise
                if self._requested:
                    _LOGGER.debug("Retrying Volcano connection in %s seconds", delay)
                    await self._wait_retry(delay)
                    delay = min(delay * 2, MAX_RECONNECT_INTERVAL)
        except Exception:
            _LOGGER.exception("Unexpected Volcano Bluetooth error; connection stopped")
        finally:
            self._requested = False
            self._invalidate()

    async def _wait_retry(self, delay: float) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self._retry_now.wait(), delay)

    async def _connect(self) -> None:
        """Resolve through HA so local adapters and Bluetooth proxies work."""
        self._publish(bt_status=BT_STATUS_CONNECTING)
        # Normalize only the lookup; legacy entity IDs retain their original spelling.
        device = async_ble_device_from_address(self.hass, self.bt_address.upper(), connectable=True)
        if device is None:
            raise BleakError("No connectable advertisement is available")
        async with self._io_lock:
            # The connector owns its attempt timeouts and retry budget. An outer
            # 30-second deadline used to interrupt those retries. User Disconnect
            # and unload can still cancel this worker immediately.
            self._client = await establish_connection(
                BleakClientWithServiceCache,
                device,
                self.bt_address,
                disconnected_callback=self._on_disconnect,
                use_services_cache=self._use_services_cache,
            )
            # A connection can succeed with an incomplete cached service table.
            # Do not enter a retry loop that keeps accepting the same table.
            for uuid in (UUID_TEMP, UUID_PUMP_NOTIFICATIONS):
                if self._client.services.get_characteristic(uuid) is None:
                    raise BleakCharacteristicNotFoundError(uuid)
            self._generation += 1
            await self._read_temperature()
            await self._read_setpoint()
            await self._read_fields((*METADATA_READS, *SETTINGS_READS))
            client = self._client
            async with asyncio.timeout(IO_TIMEOUT):
                await client.start_notify(
                    UUID_PUMP_NOTIFICATIONS,
                    lambda sender, data: self._notification(client, data),
                )
            # Subscribe before reading to avoid missing a change during setup.
            # A notification received during the read is newer than its response.
            status_sequence = self._status_sequence
            data = await self._read_optional(UUID_PUMP_NOTIFICATIONS)
            if data is not None and status_sequence == self._status_sequence:
                self._update_status(data)
            characteristic = client.services.get_characteristic(REGISTER2_UUID)
            if characteristic is not None and "notify" in characteristic.properties:
                try:
                    async with asyncio.timeout(IO_TIMEOUT):
                        await client.start_notify(
                            REGISTER2_UUID,
                            lambda sender, data: self._unit_notification(client, data),
                        )
                except (BleakError, TimeoutError, OSError, EOFError) as err:
                    _LOGGER.debug("Temperature unit notifications unavailable; polling: %s", err)
            await self._read_temperature_unit()
            if not client.is_connected or self._disconnected.is_set():
                raise BleakError("Disconnected during initialization")
            self._use_services_cache = True
            self._publish(bt_status=BT_STATUS_CONNECTED)

    async def _clear_service_cache(self) -> None:
        """Discard incomplete services before the worker disconnects and retries."""
        self._use_services_cache = False
        self._disconnected.set()
        self._invalidate()
        if self._client is None:
            return
        try:
            async with asyncio.timeout(IO_TIMEOUT):
                await self._client.clear_cache()
        except (BleakError, TimeoutError, OSError, EOFError) as err:
            _LOGGER.debug("Volcano Bluetooth service cache could not be cleared: %s", err)

    @callback
    def _on_disconnect(self, client: BleakClient) -> None:
        """Bleak requires a synchronous disconnect callback."""
        if client is self._client:
            self._disconnected.set()
            self._invalidate()

    @callback
    def _notification(self, client: BleakClient, data: bytearray) -> None:
        if client is self._client and not self._disconnected.is_set():
            self._status_sequence += 1
            self._update_status(data)
            self._outputs_notified_off = (
                self.state.heat_state is False and self.state.pump_state is False
            )

    @callback
    def _unit_notification(self, client: BleakClient, data: bytearray) -> None:
        if client is self._client and not self._disconnected.is_set():
            self._unit_sequence += 1
            self._unit_notification_received = True
            self._update_temperature_unit(data)

    @callback
    def _update_temperature_unit(self, data: bytes | bytearray | None) -> None:
        self._unit_write_acknowledged = False
        try:
            unit = decode_temperature_unit(data) if data is not None else None
        except ProtocolError:
            unit = None
        self._publish(temperature_unit=unit, temperature_unit_fallback=None)

    async def _read_temperature_unit(self) -> None:
        sequence = self._unit_sequence
        data = await self._read_optional(REGISTER2_UUID)
        if sequence == self._unit_sequence and not self._disconnected.is_set():
            if data is not None:
                self._update_temperature_unit(data)
            elif not self._unit_notification_received and not self._unit_write_acknowledged:
                # The wire format is always Celsius. Use it until notify-only
                # firmware reports a unit, without claiming its display uses C.
                self._publish(temperature_unit=None, temperature_unit_fallback="C")

    @callback
    def _update_status(self, data: bytes | bytearray) -> None:
        self._status_received = True
        try:
            status = decode_status(data)
        except ProtocolError:
            self._outputs_notified_off = False
            self._publish(heat_state=None, pump_state=None, raw_status=data.hex())
        else:
            if status.heat or status.pump:
                self._outputs_notified_off = False
            self._publish(heat_state=status.heat, pump_state=status.pump, raw_status=status.raw)

    async def _disconnect(self) -> None:
        async with self._io_lock:
            client, self._client = self._client, None
            self._invalidate()
            if client is not None:
                try:
                    async with asyncio.timeout(IO_TIMEOUT):
                        await client.disconnect()
                except (BleakError, TimeoutError, OSError, EOFError) as err:
                    _LOGGER.debug("Volcano disconnect: %s", err)

    async def _read(self, uuid: str) -> bytearray:
        if self._client is None or not self._client.is_connected:
            raise BleakError("Volcano is disconnected")
        async with asyncio.timeout(IO_TIMEOUT):
            return await self._client.read_gatt_char(uuid)

    async def _read_optional(self, uuid: str) -> bytearray | None:
        characteristic = self._client.services.get_characteristic(uuid)
        if characteristic is None or "read" not in characteristic.properties:
            return None
        return await self._read(uuid)

    async def _read_fields(self, fields: tuple[tuple[str, str, Callable], ...]) -> None:
        """Refresh optional values under the I/O lock and publish one snapshot."""
        updates = {}
        for uuid, field, decoder in fields:
            data = await self._read_optional(uuid)
            try:
                updates[field] = decoder(data) if data is not None else None
            except ProtocolError:
                updates[field] = None
                _LOGGER.debug("Invalid optional characteristic %s", uuid)
        self._publish(**updates)
        if firmware := updates.get("firmware_version"):
            registry = dr.async_get(self.hass)
            identifier = (DOMAIN, self.bt_address)
            if lookup := getattr(registry, "async_get_device_by_identifier", None):
                device = lookup(identifier, self._config_entry_id)
            else:
                # Older HA has no scoped identifier lookup; restrict the search to this entry.
                device = next(
                    (
                        device
                        for device in dr.async_entries_for_config_entry(
                            registry, self._config_entry_id
                        )
                        if identifier in device.identifiers
                    ),
                    None,
                )
            if device is not None and device.sw_version != firmware:
                registry.async_update_device(device.id, sw_version=firmware)

    async def _read_temperature(self) -> None:
        value = decode_temperature(await self._read(UUID_TEMP))
        self._temperature_sequence += 1
        self._temperature_read_at = asyncio.get_running_loop().time()
        self._publish(current_temperature=value)

    async def _read_setpoint(self) -> None:
        data = await self._read_optional(UUID_HEATER_SETPOINT)
        if data is not None:
            self._publish(target_temperature=decode_temperature(data))

    async def _write(self, uuid: str, payload: bytes) -> bool:
        """Write a command and return whether the device acknowledged it."""
        characteristic = self._client.services.get_characteristic(uuid)
        if characteristic is None:
            raise HomeAssistantError(f"Volcano characteristic {uuid} is unavailable")
        if not {"write", "write-without-response"}.intersection(characteristic.properties):
            raise HomeAssistantError(f"Volcano characteristic {uuid} is not writable")
        if uuid in (UUID_HEAT_ON, UUID_PUMP_ON):
            # An earlier OFF notification cannot confirm a later shutdown once
            # an ON command has been sent, even if its notification is delayed.
            self._outputs_notified_off = False
        # A write without response is sent, but not acknowledged by the device.
        acknowledged = "write" in characteristic.properties
        async with asyncio.timeout(IO_TIMEOUT):
            await self._client.write_gatt_char(characteristic, payload, response=acknowledged)
        if uuid in (UUID_HEAT_ON, UUID_PUMP_ON):
            # An OFF notification delivered during the write can precede the ON.
            self._outputs_notified_off = False
        return acknowledged

    async def _command(self, operation: Callable, **updates: Any) -> tuple[int, int]:
        """Serialize all commands with polling; failed writes never look successful."""
        try:
            async with self._io_lock:
                if not self.connected:
                    raise HomeAssistantError("Volcano is not connected")
                await operation()
                if not self.connected:
                    raise HomeAssistantError("Volcano disconnected during the command")
                self._publish(**updates)
                return self._generation, self._temperature_sequence
        except CONNECTION_ERRORS as err:
            self._disconnected.set()
            self._invalidate()
            raise HomeAssistantError(f"Volcano command failed: {err}") from err

    async def write_gatt_command(self, uuid: str, payload: bytes = b"") -> None:
        await self._command(lambda: self._write(uuid, payload))

    async def set_heater_temperature(
        self, temperature: float, *, wait: bool = False, unit: str = "C"
    ) -> None:
        payload = encode_temperature(temperature, unit)
        generation, sequence = await self._command(
            lambda: self._write(UUID_HEATER_SETPOINT, payload),
            target_temperature=decode_temperature(payload),
        )
        if wait:
            await self.wait_for_temperature(decode_temperature(payload), generation, sequence)

    async def set_led_brightness(self, brightness: int) -> None:
        if not MIN_BRIGHTNESS <= brightness <= MAX_BRIGHTNESS:
            raise ValueError("Brightness must be between 0 and 100")
        await self._command(
            lambda: self._write(UUID_LED_BRIGHTNESS, brightness.to_bytes(2, "little")),
            led_brightness=brightness,
        )

    async def set_auto_shutoff_setting(self, minutes: int) -> None:
        if not MIN_SHUTOFF_MINUTES <= minutes <= MAX_SHUTOFF_MINUTES:
            raise ValueError(
                f"Auto shutoff must be {MIN_SHUTOFF_MINUTES}–{MAX_SHUTOFF_MINUTES} minutes"
            )
        await self._command(
            lambda: self._write(UUID_AUTO_SHUT_OFF_SETTING, (minutes * 60).to_bytes(2, "little")),
            auto_shut_off_setting=minutes,
        )

    async def set_vibration(self, enabled: bool) -> None:
        async def write_register() -> None:
            await self._write(REGISTER3_UUID, encode_vibration(enabled))
            actual = decode_vibration(await self._read(REGISTER3_UUID))
            self._publish(vibration=actual)
            if actual != enabled:
                raise HomeAssistantError("Volcano did not confirm the vibration setting")

        await self._command(write_register)

    async def set_temperature_unit(self, unit: str) -> None:
        payload = encode_temperature_unit(unit)

        async def write_register() -> None:
            acknowledged = await self._write(REGISTER2_UUID, payload)
            await self._read_temperature_unit()
            if self.state.temperature_unit == unit:
                return
            characteristic = self._client.services.get_characteristic(REGISTER2_UUID)
            if (
                characteristic is not None
                and "notify" in characteristic.properties
                and "read" not in characteristic.properties
            ):
                # Notifications do not take the I/O lock, so confirmation can
                # arrive while other commands remain queued behind this change.
                try:
                    async with asyncio.timeout(IO_TIMEOUT):
                        while True:
                            changed = self._changed
                            if not self.connected:
                                raise HomeAssistantError(
                                    "Volcano disconnected while confirming the temperature unit"
                                )
                            if self.state.temperature_unit == unit:
                                return
                            await changed.wait()
                except TimeoutError as err:
                    if self.connected and acknowledged and not self._unit_notification_received:
                        # Selecting the existing unit need not produce a notification.
                        # Use the acknowledged setting until the device reports one.
                        self._unit_write_acknowledged = True
                        self._publish(temperature_unit=unit, temperature_unit_fallback=None)
                        return
                    raise HomeAssistantError(
                        "Volcano did not confirm the temperature unit"
                    ) from err
            raise HomeAssistantError("Volcano did not confirm the temperature unit")

        await self._command(write_register)

    async def wait_until_connected(self, timeout: float = CONNECT_WAIT_TIMEOUT) -> None:
        try:
            async with asyncio.timeout(timeout):
                while True:
                    changed = self._changed
                    if self.connected:
                        return
                    if not self._requested:
                        raise HomeAssistantError("Volcano connection was stopped")
                    await changed.wait()
        except TimeoutError as err:
            raise HomeAssistantError(
                f"Timed out connecting to the Volcano after {timeout:g} seconds. "
                "Connection retries continue; use Disconnect to stop them or increase "
                "the connect action timeout."
            ) from err

    async def wait_for_temperature(
        self,
        target: float,
        generation: int,
        sequence: int,
        timeout: float = TEMPERATURE_TIMEOUT,
    ) -> None:
        """Preserve 'reaches or exceeds' semantics using fresh same-session samples."""
        try:
            async with asyncio.timeout(timeout):
                while True:
                    changed = self._changed
                    if not self.connected or generation != self._generation:
                        raise HomeAssistantError(
                            "Volcano disconnected while waiting for temperature"
                        )
                    if self.state.target_temperature != target:
                        raise HomeAssistantError("Volcano temperature target changed while waiting")
                    if (
                        self._temperature_sequence > sequence
                        and self._temperature_read_at is not None
                        and asyncio.get_running_loop().time() - self._temperature_read_at
                        <= 5 * TEMP_POLL_INTERVAL
                        and self.state.current_temperature is not None
                        and self.state.current_temperature >= target
                    ):
                        return
                    await changed.wait()
        except TimeoutError as err:
            raise HomeAssistantError(
                f"Timed out waiting for Volcano temperature {target} °C"
            ) from err
