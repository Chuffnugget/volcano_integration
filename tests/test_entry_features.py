"""Tests for service readiness, configuration, diagnostics and metadata."""

import asyncio
import json
from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.volcano_integration import SERVICE_SCHEMAS
from custom_components.volcano_integration.bluetooth_coordinator import METADATA_READS
from custom_components.volcano_integration.const import (
    DOMAIN,
    REGISTER3_UUID,
    UUID_FIRMWARE_VERSION,
    UUID_HEATER_SETPOINT,
)
from custom_components.volcano_integration.diagnostics import async_get_config_entry_diagnostics

from .conftest import connect_manager, drain


@pytest.mark.parametrize(
    "error", [ImportError("Frontend API changed"), FileNotFoundError("Bundle")]
)
async def test_broken_card_does_not_block_device_or_services(
    hass, entry, ble, frontend_setup, error, caplog
):
    frontend_setup.side_effect = error
    with patch("homeassistant.setup.async_process_deps_reqs", return_value=True):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()
    try:
        assert "Bluetooth controls remain available" in caplog.text
        await hass.services.async_call(DOMAIN, "connect", {}, blocking=True)
        assert entry.runtime_data.connected
        await hass.services.async_call(DOMAIN, "pump_on", {}, blocking=True)
    finally:
        await hass.config_entries.async_unload(entry.entry_id)


async def test_temperature_service_rounds_before_writing(hass, integration, peripheral):
    await connect_manager(integration)
    await hass.services.async_call(
        DOMAIN,
        "set_temperature",
        {"temperature": 170.6, "wait_until_reached": False},
        blocking=True,
    )
    assert integration.state.target_temperature == 171
    assert peripheral.values[UUID_HEATER_SETPOINT] == (1710).to_bytes(4, "little")


async def test_connect_action_waits_for_initial_reads_and_honors_timeout(
    hass, integration, peripheral
):
    assert SERVICE_SCHEMAS["connect"]({})["timeout"] == 180
    started, release = asyncio.Event(), asyncio.Event()
    original = peripheral.read_gatt_char.side_effect

    async def slow_metadata(uuid):
        if uuid == UUID_FIRMWARE_VERSION:
            started.set()
            await release.wait()
        return await original(uuid)

    peripheral.read_gatt_char.side_effect = slow_metadata
    call = asyncio.create_task(
        hass.services.async_call(DOMAIN, "connect", {"timeout": 1}, blocking=True)
    )
    await started.wait()
    assert not integration.connected
    assert not call.done()
    with pytest.raises(HomeAssistantError, match="retries continue"):
        await call
    assert integration.connection_requested
    release.set()
    await integration.wait_until_connected(timeout=2)
    await hass.services.async_call(
        DOMAIN,
        "set_temperature",
        {"temperature": 180.5, "wait_until_reached": False},
        blocking=True,
    )
    assert integration.state.target_temperature == 181


async def test_connector_can_finish_its_own_retry_budget(manager, ble, monkeypatch):
    original_connect = ble.side_effect
    original_timeout = asyncio.timeout

    # Scale the former 30-second deadline down so this reproduces the old bug
    # quickly, without altering the connector or I/O timeout budgets.
    monkeypatch.setattr(
        asyncio, "timeout", lambda delay: original_timeout(0.01 if delay == 30 else delay)
    )

    async def slow_connector(*args, **kwargs):
        await asyncio.sleep(0.03)
        return await original_connect(*args, **kwargs)

    ble.side_effect = slow_connector
    await connect_manager(manager)
    assert manager.connected
    assert ble.await_count == 1


async def test_vibration_switch_uses_confirmed_state(hass, integration, peripheral):
    entity_id = er.async_get(hass).async_get_entity_id(
        "switch", DOMAIN, "volcano_vibration_AA:BB:CC:DD:EE:FF"
    )
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "unavailable"
    await connect_manager(integration)
    await hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
    assert hass.states.get(entity_id).state == "off"
    assert int.from_bytes(peripheral.values[REGISTER3_UUID], "little") & 0x0400
    await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
    assert hass.states.get(entity_id).state == "on"
    peripheral.write_gatt_char.side_effect = None
    with pytest.raises(HomeAssistantError, match="did not confirm"):
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": entity_id}, blocking=True
        )
    assert hass.states.get(entity_id).state == "on"
    await integration.stop()
    assert hass.states.get(entity_id).state == "unavailable"


async def test_firmware_registry_updates_only_on_metadata_read(
    hass, entry, integration, peripheral
):
    registry = dr.async_get(hass)
    with patch.object(
        registry, "async_update_device", wraps=registry.async_update_device
    ) as update:
        await connect_manager(integration)
        assert update.call_count == 1
        assert update.call_args.kwargs == {"sw_version": "1.9"}
        update.reset_mock()
        lookup_owner, lookup_name = (
            (registry, "async_get_device_by_identifier")
            if hasattr(registry, "async_get_device_by_identifier")
            else (dr, "async_entries_for_config_entry")
        )
        with patch.object(
            lookup_owner, lookup_name, wraps=getattr(lookup_owner, lookup_name)
        ) as lookup:
            for temp in (175, 180, 185):
                integration._publish(current_temperature=temp)
            await drain()
            lookup.assert_not_called()
        update.assert_not_called()
        peripheral.values[UUID_FIRMWARE_VERSION] = b"2.0"
        async with integration._io_lock:
            await integration._read_fields(METADATA_READS)
        update.assert_called_once()
        device = dr.async_entries_for_config_entry(registry, entry.entry_id)[0]
        assert device.sw_version == "2.0"


async def test_firmware_read_avoids_deprecated_device_lookup(
    hass, entry, integration, peripheral, caplog
):
    await connect_manager(integration)
    registry = dr.async_get(hass)
    peripheral.values[UUID_FIRMWARE_VERSION] = b"2.0"
    with patch.object(
        registry,
        "async_get_device",
        side_effect=AssertionError("Deprecated device lookup called"),
    ):
        async with integration._io_lock:
            await integration._read_fields(METADATA_READS)
    device = dr.async_entries_for_config_entry(registry, entry.entry_id)[0]
    assert device.sw_version == "2.0"
    assert "calls `device_registry.async_get_device`" not in caplog.text


@pytest.mark.parametrize("own_device_exists", [False, True])
async def test_firmware_update_stays_with_own_entry(hass, entry, manager, own_device_exists):
    registry = dr.async_get(hass)
    if own_device_exists and not hasattr(registry, "async_get_device_by_identifier"):
        pytest.skip("Older HA merges devices with identical identifiers across entries")
    other_entry = MockConfigEntry(domain=DOMAIN, version=2, data={})
    other_entry.add_to_hass(hass)
    identifier = (DOMAIN, entry.data["bt_address"])
    other_device = registry.async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={identifier},
        sw_version="other firmware",
    )
    own_device = None
    if own_device_exists:
        own_device = registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={identifier},
            sw_version="old firmware",
        )
        assert own_device.id != other_device.id
    await connect_manager(manager)
    assert registry.async_get(other_device.id).sw_version == "other firmware"
    if own_device is not None:
        assert registry.async_get(own_device.id).sw_version == "1.9"


async def test_diagnostics_redact_identity_and_keep_useful_state(hass, entry, integration):
    await connect_manager(integration)
    result = await async_get_config_entry_diagnostics(hass, entry)
    serialized = json.dumps(result)
    assert entry.data["bt_address"] not in serialized
    assert entry.data["device_name"] not in serialized
    assert integration.state.serial_number not in serialized
    assert entry.entry_id not in serialized
    assert result["state"]["serial_number"] == "**REDACTED**"
    assert result["state"]["firmware_version"] == "1.9"
    assert result["connected"] is True
    assert entry.runtime_data is integration


async def test_legacy_entry_gets_repair_without_changing_data(hass, ble):
    legacy = MockConfigEntry(
        domain=DOMAIN,
        title="Old Volcano",
        version=1,
        data={"mac_address": "AA:BB:CC:DD:EE:FF", "name": "Original"},
    )
    legacy.add_to_hass(hass)
    original = dict(legacy.data)
    with patch("homeassistant.setup.async_process_deps_reqs", return_value=True):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()
    issue_id = f"legacy_entry_{legacy.entry_id}"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_key == "legacy_configuration"
    assert legacy.version == 1
    assert dict(legacy.data) == original
    ble.assert_not_awaited()
    await hass.config_entries.async_remove(legacy.entry_id)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_bluetooth_enum_keeps_existing_states(hass, integration):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, "volcano_bt_status_AA:BB:CC:DD:EE:FF"
    )
    state = hass.states.get(entity_id)
    assert state.state == "DISCONNECTED"
    assert state.attributes["device_class"] == "enum"
    assert state.attributes["options"] == ["DISCONNECTED", "CONNECTING", "CONNECTED"]
    await connect_manager(integration)
    assert hass.states.get(entity_id).state == "CONNECTED"
