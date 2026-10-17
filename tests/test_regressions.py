"""Regression tests for lifecycle, concurrency and device I/O failures."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, UnitOfTemperature
from homeassistant.exceptions import ConfigEntryError, HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.volcano_integration import async_setup_entry, async_unload_entry
from custom_components.volcano_integration.const import (
    DOMAIN,
    MAX_SHUTOFF_MINUTES,
    MIN_SHUTOFF_MINUTES,
    UUID_AUTO_SHUT_OFF_SETTING,
    UUID_LED_BRIGHTNESS,
    UUID_PUMP_NOTIFICATIONS,
    UUID_PUMP_OFF,
    UUID_PUMP_ON,
)

from .conftest import connect_manager, drain


async def test_connect_queued_during_unload_cannot_restart_worker(
    hass, entry, integration, peripheral
):
    await connect_manager(integration)
    started, release = asyncio.Event(), asyncio.Event()
    original_disconnect = peripheral.disconnect.side_effect

    async def disconnect():
        started.set()
        await release.wait()
        await original_disconnect()

    peripheral.disconnect.side_effect = disconnect
    unload_task = asyncio.create_task(hass.config_entries.async_unload(entry.entry_id))
    await started.wait()
    # A previously resolved service handler can still hold this manager reference.
    connect_task = asyncio.create_task(integration.async_user_connect())
    await drain()
    release.set()
    try:
        assert await unload_task
        with pytest.raises(HomeAssistantError, match="unloaded|shutting down"):
            await connect_task
        assert not integration.connection_requested
        assert integration._run_task is None
    finally:
        await integration.stop()


async def test_cancelled_setup_removes_runtime_and_stops_connection(hass, entry, ble):
    started = asyncio.Event()
    managers = []

    async def forward(*args):
        manager = hass.data[DOMAIN][entry.entry_id]
        managers.append(manager)
        await connect_manager(manager)
        started.set()
        await asyncio.Event().wait()

    with patch.object(hass.config_entries, "async_forward_entry_setups", side_effect=forward):
        task = asyncio.create_task(async_setup_entry(hass, entry))
        await started.wait()
        task.cancel()
        try:
            with pytest.raises(asyncio.CancelledError):
                await task
            assert entry.entry_id not in hass.data[DOMAIN]
            assert managers[0]._run_task is None
        finally:
            await managers[0].stop()
            hass.data[DOMAIN].pop(entry.entry_id, None)


async def test_legacy_duplicate_entries_do_not_open_two_managers(hass, entry, integration):
    duplicate = MockConfigEntry(
        domain=DOMAIN,
        title="Old duplicate",
        version=2,
        data={"bt_address": entry.data["bt_address"].lower()},
    )
    duplicate.add_to_hass(hass)
    with patch("homeassistant.setup.async_process_deps_reqs", return_value=True):
        try:
            assert not await hass.config_entries.async_setup(duplicate.entry_id)
            assert duplicate.entry_id not in hass.data[DOMAIN]
            assert hass.data[DOMAIN][entry.entry_id] is integration
        finally:
            if duplicate.entry_id in hass.data[DOMAIN]:
                await hass.config_entries.async_unload(duplicate.entry_id)


async def test_status_changed_during_subscription_is_not_missed(manager, peripheral):
    original_notify = peripheral.start_notify.side_effect

    async def notify(uuid, callback):
        peripheral.values[UUID_PUMP_NOTIFICATIONS] = bytes.fromhex("0020")
        await original_notify(uuid, callback)

    peripheral.start_notify.side_effect = notify
    await connect_manager(manager)
    assert manager.state.pump_state is True
    assert manager.state.heat_state is False


async def test_failing_entity_listener_does_not_break_bluetooth(manager, peripheral, caplog):
    await connect_manager(manager)
    broken = Mock(side_effect=ValueError("Broken entity update"))
    healthy = Mock()
    unsubscribers = [manager.async_add_listener(broken), manager.async_add_listener(healthy)]
    try:
        peripheral.notification_callback(None, bytes.fromhex("0020"))
        assert manager.connected
        assert manager.state.pump_state is True
        healthy.assert_called_once()
        assert "Broken entity update" in caplog.text
    finally:
        for unsubscribe in unsubscribers:
            unsubscribe()


async def test_number_rounds_converted_temperature_to_whole_celsius(hass, integration):
    await connect_manager(integration)
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "number", DOMAIN, "volcano_heater_temperature_setpoint_AA:BB:CC:DD:EE:FF"
    )
    registry.async_update_entity_options(
        entity_id, "number", {"unit_of_measurement": UnitOfTemperature.FAHRENHEIT}
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).attributes["unit_of_measurement"] == "°F"
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 350}, blocking=True
    )
    # 350 F is 176.666... C; this device is set to Celsius, so it rounds to 177 C.
    assert integration.state.target_temperature == 177


@pytest.mark.parametrize("raw", [b"\x14", b"\xff\xff", b"\x65\x00"])
async def test_malformed_brightness_is_unknown(manager, peripheral, raw):
    peripheral.values[UUID_LED_BRIGHTNESS] = raw
    await connect_manager(manager)
    assert manager.state.led_brightness is None
    assert manager.connected


async def test_shutdown_prevents_late_service_from_restarting(hass, integration, peripheral):
    await connect_manager(integration)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    assert not integration.connected
    peripheral.disconnect.assert_awaited_once()
    with pytest.raises(HomeAssistantError, match="shutting down"):
        await integration.async_user_connect()


async def test_user_disconnect_still_allows_reconnect(manager, ble):
    await connect_manager(manager)
    await manager.async_user_disconnect()
    await connect_manager(manager)
    assert manager.connected
    assert ble.await_count == 2


async def test_new_status_notification_wins_over_older_initial_read(manager, peripheral):
    original_read = peripheral.read_gatt_char.side_effect

    async def read(uuid):
        if uuid == UUID_PUMP_NOTIFICATIONS:
            peripheral.notification_callback(None, bytes.fromhex("0020"))
            return bytes.fromhex("2300")
        return await original_read(uuid)

    peripheral.read_gatt_char.side_effect = read
    await connect_manager(manager)
    assert manager.state.pump_state is True
    assert manager.state.heat_state is False


async def test_poll_programming_error_is_logged_and_does_not_break_stop(
    manager, peripheral, caplog
):
    await connect_manager(manager)
    peripheral.read_gatt_char.side_effect = RuntimeError("Unexpected backend failure")
    task = manager._run_task
    await asyncio.wait_for(asyncio.shield(task), 2)
    await manager.stop()
    assert not manager.connected
    assert not manager.connection_requested
    assert "Unexpected backend failure" in caplog.text
    peripheral.disconnect.assert_awaited_once()


async def test_write_timeout_fails_action_and_invalidates_state(manager, peripheral, monkeypatch):
    await connect_manager(manager)
    monkeypatch.setattr(
        "custom_components.volcano_integration.bluetooth_coordinator.IO_TIMEOUT", 0.01
    )

    async def blocked(*args, **kwargs):
        await asyncio.Event().wait()

    peripheral.write_gatt_char.side_effect = blocked
    with pytest.raises(HomeAssistantError, match="command failed"):
        await manager.set_led_brightness(50)
    assert manager.state.led_brightness is None
    assert not manager.connected


async def test_disconnect_timeout_is_bounded(manager, peripheral, monkeypatch):
    await connect_manager(manager)
    monkeypatch.setattr(
        "custom_components.volcano_integration.bluetooth_coordinator.IO_TIMEOUT", 0.01
    )

    async def blocked():
        await asyncio.Event().wait()

    peripheral.disconnect.side_effect = blocked
    await asyncio.wait_for(manager.stop(), 1)
    assert manager._client is None
    assert manager._run_task is None
    assert not manager.connection_requested


async def test_optional_characteristics_and_invalid_text_do_not_prevent_connection(
    manager, peripheral
):
    from custom_components.volcano_integration.const import (
        UUID_FIRMWARE_VERSION,
        UUID_SERIAL_NUMBER,
    )

    original = peripheral.characteristic
    peripheral.services.get_characteristic = lambda uuid: (
        None if uuid == UUID_SERIAL_NUMBER else original(uuid)
    )
    peripheral.values[UUID_FIRMWARE_VERSION] = b"\xff\xfe"
    await connect_manager(manager)
    assert manager.connected
    assert manager.state.serial_number is None
    assert manager.state.firmware_version is None


@pytest.mark.parametrize(
    "properties, response", [(["write"], True), (["write-without-response"], False)]
)
async def test_advertised_write_mode_is_respected(manager, peripheral, properties, response):
    await connect_manager(manager)
    peripheral.services.get_characteristic = lambda uuid: SimpleNamespace(
        uuid=uuid, properties=properties
    )
    await manager.write_gatt_command(UUID_PUMP_OFF, b"\x00")
    assert peripheral.write_gatt_char.call_args.kwargs == {"response": response}


async def test_missing_command_characteristic_fails_without_writing(manager, peripheral):
    await connect_manager(manager)
    peripheral.services.get_characteristic = lambda uuid: None
    with pytest.raises(HomeAssistantError, match="unavailable"):
        await manager.write_gatt_command(UUID_PUMP_ON, b"\x01")
    peripheral.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("minutes", [MIN_SHUTOFF_MINUTES, MAX_SHUTOFF_MINUTES])
async def test_shutoff_service_boundary_wire_units(hass, integration, peripheral, minutes):
    await connect_manager(integration)
    await hass.services.async_call(
        DOMAIN, "set_auto_shutoff_setting", {"minutes": minutes}, blocking=True
    )
    assert peripheral.values[UUID_AUTO_SHUT_OFF_SETTING] == (minutes * 60).to_bytes(2, "little")
    assert integration.state.auto_shut_off_setting == minutes


@pytest.mark.parametrize("device_ids", [None, [], ["missing"], ["first", "second"]])
async def test_invalid_device_target_never_writes(hass, integration, peripheral, device_ids):
    await connect_manager(integration)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "pump_on", {"device_id": device_ids}, blocking=True)
    peripheral.write_gatt_char.assert_not_awaited()


async def test_concurrent_duplicate_entry_setup_reserves_one_manager(hass, entry, frontend_setup):
    duplicate = MockConfigEntry(
        domain=DOMAIN, version=2, data={"bt_address": entry.data["bt_address"].lower()}
    )
    duplicate.add_to_hass(hass)

    async def yielding_frontend(hass):
        await asyncio.sleep(0)

    frontend_setup.side_effect = yielding_frontend
    with (
        patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        patch.object(hass.config_entries, "async_unload_platforms", return_value=True),
    ):
        results = await asyncio.gather(
            async_setup_entry(hass, entry),
            async_setup_entry(hass, duplicate),
            return_exceptions=True,
        )
        try:
            assert results.count(True) == 1
            assert sum(isinstance(result, ConfigEntryError) for result in results) == 1
            assert len(hass.data[DOMAIN]) == 1
        finally:
            for configured in (entry, duplicate):
                if configured.entry_id in hass.data[DOMAIN]:
                    await async_unload_entry(hass, configured)


async def test_retry_request_remains_visible_and_can_be_cancelled(hass, integration, monkeypatch):
    retrying = asyncio.Event()

    async def wait_retry(delay):
        retrying.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(
        "custom_components.volcano_integration.bluetooth_coordinator.async_ble_device_from_address",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(integration, "_wait_retry", wait_retry)
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, "volcano_bt_status_AA:BB:CC:DD:EE:FF"
    )
    await integration.async_user_connect()
    await retrying.wait()
    state = hass.states.get(entity_id)
    assert state.state == "DISCONNECTED"
    assert state.attributes["connection_requested"] is True
    await integration.async_user_disconnect()
    assert hass.states.get(entity_id).attributes["connection_requested"] is False


async def test_cancelled_frontend_setup_releases_reserved_manager(hass, entry, frontend_setup):
    managers = []

    async def cancel_frontend(hass):
        managers.append(entry.runtime_data)
        raise asyncio.CancelledError

    frontend_setup.side_effect = cancel_frontend
    with pytest.raises(asyncio.CancelledError):
        await async_setup_entry(hass, entry)
    assert entry.entry_id not in hass.data[DOMAIN]
    assert not hasattr(entry, "runtime_data")
    with pytest.raises(HomeAssistantError, match="unloaded|shutting down"):
        await managers[0].async_user_connect()


async def test_real_buttons_connect_pump_and_disconnect(hass, integration, peripheral):
    registry = er.async_get(hass)
    for key in ("connect", "pump_on", "disconnect"):
        entity_id = registry.async_get_entity_id(
            "button", DOMAIN, f"volcano_{key}_button_AA:BB:CC:DD:EE:FF"
        )
        await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)
        if key == "connect":
            await integration.wait_until_connected(timeout=1)
    assert peripheral.values[UUID_PUMP_ON] == b"\x01"
    assert not integration.connected


async def test_read_only_characteristic_is_never_written(manager, peripheral):
    await connect_manager(manager)
    peripheral.services.get_characteristic = lambda uuid: SimpleNamespace(
        uuid=uuid, properties=["read"]
    )
    with pytest.raises(HomeAssistantError, match="not writable"):
        await manager.write_gatt_command(UUID_PUMP_ON, b"\x01")
    peripheral.write_gatt_char.assert_not_awaited()
    assert manager.connected


@pytest.mark.parametrize("error", [RuntimeError("Platform setup failed"), asyncio.CancelledError()])
async def test_failed_setup_cleans_partial_entities_and_can_reload(hass, entry, ble, error):
    original_forward = hass.config_entries.async_forward_entry_setups
    managers = []

    async def partial_setup(*args):
        await original_forward(*args)
        manager = hass.data[DOMAIN][entry.entry_id]
        managers.append(manager)
        await connect_manager(manager)
        assert len(manager._listeners) == 21
        raise error

    with (
        patch("homeassistant.setup.async_process_deps_reqs", return_value=True),
        patch.object(hass.config_entries, "async_forward_entry_setups", side_effect=partial_setup),
    ):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()
    assert entry.entry_id not in hass.data[DOMAIN]
    assert not managers[0]._listeners
    assert managers[0]._run_task is None
    with patch("homeassistant.setup.async_process_deps_reqs", return_value=True):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        try:
            assert hass.data[DOMAIN][entry.entry_id] is not managers[0]
            assert len(hass.data[DOMAIN][entry.entry_id]._listeners) == 21
        finally:
            await hass.config_entries.async_unload(entry.entry_id)
