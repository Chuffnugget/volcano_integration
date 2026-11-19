"""Keep whole native minutes when Home Assistant converts duration units."""

import pytest
from homeassistant.components.number import UNIT_CONVERTERS, NumberDeviceClass
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.volcano_integration.const import DOMAIN, UUID_AUTO_SHUT_OFF_SETTING

from .conftest import connect_manager, drain


async def shutoff_entity(hass, integration, unit):
    if unit != "min" and NumberDeviceClass.DURATION not in UNIT_CONVERTERS:
        pytest.skip("This HA version does not support duration number unit conversion")
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "number", DOMAIN, "volcano_auto_shutoff_minutes_AA:BB:CC:DD:EE:FF"
    )
    registry.async_update_entity_options(entity_id, "number", {"unit_of_measurement": unit})
    await drain()
    await connect_manager(integration)
    assert hass.states.get(entity_id).attributes["unit_of_measurement"] == unit
    return entity_id


@pytest.mark.parametrize(("unit", "factor"), [("min", 1), ("s", 60), ("h", 1 / 60)])
@pytest.mark.parametrize("minutes", [30, 120, 123, 246, 360])
async def test_shutoff_units_preserve_whole_minutes(
    hass, integration, peripheral, unit, factor, minutes
):
    entity_id = await shutoff_entity(hass, integration, unit)
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": minutes * factor}, blocking=True
    )
    assert int.from_bytes(peripheral.values[UUID_AUTO_SHUT_OFF_SETTING], "little") == minutes * 60
    assert integration.state.auto_shut_off_setting == minutes
    await hass.async_block_till_done()
    attrs = hass.states.get(entity_id).attributes
    assert attrs["native_value"] == minutes
    assert attrs["native_min_value"] == 30
    assert attrs["native_max_value"] == 360
    assert attrs["native_step"] == 1
    assert attrs["native_unit_of_measurement"] == "min"


@pytest.mark.parametrize("minutes", [-60, 361])
async def test_shutoff_hours_still_reject_out_of_range(hass, integration, peripheral, minutes):
    entity_id = await shutoff_entity(hass, integration, "h")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": entity_id, "value": minutes / 60}, blocking=True
        )
    peripheral.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize(("value", "minutes"), [(122.999999999, 123), (245.999999999, 246)])
async def test_shutoff_native_rounding(hass, integration, peripheral, value, minutes):
    entity_id = await shutoff_entity(hass, integration, "min")
    entity = hass.data["number"].get_entity(entity_id)
    await entity.async_set_native_value(value)
    assert int.from_bytes(peripheral.values[UUID_AUTO_SHUT_OFF_SETTING], "little") == minutes * 60
