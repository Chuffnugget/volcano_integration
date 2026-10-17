"""Check custom actions against Home Assistant's user permissions."""

from unittest.mock import patch

import pytest
from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_READ_ONLY, GROUP_ID_USER
from homeassistant.auth.permissions.const import CAT_ENTITIES, POLICY_CONTROL
from homeassistant.core import Context
from homeassistant.exceptions import Unauthorized, UnknownUser
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockUser

from custom_components.volcano_integration.const import (
    DOMAIN,
    UUID_AUTO_SHUT_OFF_SETTING,
    UUID_HEAT_OFF,
    UUID_HEAT_ON,
    UUID_HEATER_SETPOINT,
    UUID_LED_BRIGHTNESS,
    UUID_PUMP_OFF,
    UUID_PUMP_ON,
)

from .conftest import connect_manager

ACTIONS = [
    ("connect", {}),
    ("set_temperature", {"temperature": 190, "wait_until_reached": False}),
    ("set_led_brightness", {"brightness": 40}),
    ("set_auto_shutoff_setting", {"minutes": 60}),
    ("heat_on", {}),
    ("pump_on", {}),
    ("heat_off", {}),
    ("pump_off", {}),
    ("disconnect", {}),
]


@pytest.mark.parametrize(("service", "data"), ACTIONS)
@pytest.mark.parametrize("explicit_target", [False, True])
async def test_read_only_user_cannot_send_any_action(
    hass, entry, integration, peripheral, ble, service, data, explicit_target
):
    # The first real HA user becomes the owner, regardless of their groups.
    await hass.auth.async_create_user("Owner")
    user = await hass.auth.async_create_user("Read only", group_ids=[GROUP_ID_READ_ONLY])
    if service != "connect":
        await connect_manager(integration)
    connection_count = ble.await_count
    device = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)[0]
    target = {"device_id": device.id} if explicit_target else {}

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN, service, {**data, **target}, blocking=True, context=Context(user_id=user.id)
        )

    assert integration.connected == (service != "connect")
    assert ble.await_count == connection_count
    peripheral.write_gatt_char.assert_not_awaited()
    peripheral.disconnect.assert_not_awaited()


@pytest.mark.parametrize("group_id", [GROUP_ID_ADMIN, GROUP_ID_USER, None])
async def test_authorized_users_and_automations_can_run_all_actions(
    hass, entry, integration, peripheral, group_id
):
    context = Context()
    if group_id is not None:
        await hass.auth.async_create_user("Owner")
        user = await hass.auth.async_create_user("Controller", group_ids=[group_id])
        assert not user.is_owner
        context = Context(user_id=user.id)
    device = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)[0]

    for service, data in ACTIONS:
        await hass.services.async_call(
            DOMAIN, service, {**data, "device_id": device.id}, blocking=True, context=context
        )

    writes = {call.args[0].uuid for call in peripheral.write_gatt_char.call_args_list}
    assert {
        UUID_HEAT_ON,
        UUID_HEAT_OFF,
        UUID_PUMP_ON,
        UUID_PUMP_OFF,
        UUID_HEATER_SETPOINT,
        UUID_LED_BRIGHTNESS,
        UUID_AUTO_SHUT_OFF_SETTING,
    } <= writes
    assert int.from_bytes(peripheral.values[UUID_HEATER_SETPOINT], "little") == 1900
    assert int.from_bytes(peripheral.values[UUID_LED_BRIGHTNESS], "little") == 40
    assert int.from_bytes(peripheral.values[UUID_AUTO_SHUT_OFF_SETTING], "little") == 3600
    assert not integration.connected
    peripheral.disconnect.assert_awaited_once()


@pytest.mark.parametrize("known_user", [False, True])
async def test_unknown_or_inactive_user_cannot_send_commands(
    hass, integration, peripheral, known_user
):
    await connect_manager(integration)
    user_id = "deleted-user"
    if known_user:
        user = MockUser(is_active=False).add_to_hass(hass)
        user.mock_policy({CAT_ENTITIES: True})
        user_id = user.id

    with pytest.raises(Unauthorized if known_user else UnknownUser):
        await hass.services.async_call(
            DOMAIN, "heat_on", {}, blocking=True, context=Context(user_id=user_id)
        )

    peripheral.write_gatt_char.assert_not_awaited()


async def test_permission_is_scoped_to_action_and_device_after_entity_rename(
    hass, entry, integration, peripheral
):
    await connect_manager(integration)
    second = MockConfigEntry(
        domain=DOMAIN, title="Second Volcano", version=2, data={"bt_address": "11:22:33:44:55:66"}
    )
    second.add_to_hass(hass)
    with patch("homeassistant.setup.async_process_deps_reqs", return_value=True):
        assert await hass.config_entries.async_setup(second.entry_id)
    try:
        devices = dr.async_get(hass)
        first_device = dr.async_entries_for_config_entry(devices, entry.entry_id)[0]
        second_device = dr.async_entries_for_config_entry(devices, second.entry_id)[0]
        entities = er.async_get(hass)
        heat_off = entities.async_get_entity_id(
            "button", DOMAIN, f"volcano_heat_off_button_{entry.data['bt_address']}"
        )
        renamed = entities.async_update_entity(
            heat_off, new_entity_id="button.living_room_heat_off"
        )
        user = MockUser().add_to_hass(hass)
        user.mock_policy(
            {CAT_ENTITIES: {"entity_ids": {renamed.entity_id: {POLICY_CONTROL: True}}}}
        )
        context = Context(user_id=user.id)

        # Permission for one action must not grant any other action or device.
        for device_id, service, data in (
            (second_device.id, "heat_off", {}),
            (first_device.id, "heat_on", {}),
            (first_device.id, "set_temperature", {"temperature": 190}),
        ):
            with pytest.raises(Unauthorized):
                await hass.services.async_call(
                    DOMAIN,
                    service,
                    {"device_id": device_id, **data},
                    blocking=True,
                    context=context,
                )
        peripheral.write_gatt_char.assert_not_awaited()

        await hass.services.async_call(
            DOMAIN, "heat_off", {"device_id": first_device.id}, blocking=True, context=context
        )
        peripheral.write_gatt_char.assert_awaited_once()
        assert peripheral.write_gatt_char.call_args.args[0].uuid == UUID_HEAT_OFF
    finally:
        await hass.config_entries.async_unload(second.entry_id)


async def test_missing_entity_does_not_bypass_permissions(hass, entry, integration, peripheral):
    await connect_manager(integration)
    user = MockUser().add_to_hass(hass)
    user.mock_policy({CAT_ENTITIES: True})
    registry = er.async_get(hass)
    heat_on = registry.async_get_entity_id(
        "button", DOMAIN, f"volcano_heat_on_button_{entry.data['bt_address']}"
    )
    registry.async_remove(heat_on)

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN, "heat_on", {}, blocking=True, context=Context(user_id=user.id)
        )

    peripheral.write_gatt_char.assert_not_awaited()
