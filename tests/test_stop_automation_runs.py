"""Exercise stop-only cancellation against real Home Assistant automations."""

import asyncio
from unittest.mock import patch

import pytest
import voluptuous as vol
from homeassistant.auth.permissions.const import CAT_ENTITIES, POLICY_CONTROL
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Context, CoreState, callback
from homeassistant.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
    Unauthorized,
    UnknownUser,
)
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockUser

from custom_components.volcano_integration.const import DOMAIN
from custom_components.volcano_integration.stop_automation_runs import (
    SERVICE_STOP_AUTOMATION_RUNS,
    STOP_AUTOMATION_RUNS_SCHEMA,
)

from .conftest import drain


@pytest.fixture
async def routines(hass, integration):
    yield
    if component := hass.data.get("automation"):
        await asyncio.gather(*(entity.action_script.async_stop() for entity in component.entities))


async def load_automations(hass, mode="single", enabled=True):
    assert await async_setup_component(hass, "trace", {})
    hass.set_state(CoreState.running)
    config = []
    for name in ("selected", "unrelated"):
        config.append(
            {
                "id": f"volcano_{name}",
                "alias": f"Volcano {name}",
                "initial_state": enabled if name == "selected" else True,
                "mode": mode,
                "trigger": [{"platform": "event", "event_type": f"volcano_start_{name}"}],
                "action": [
                    {"wait_for_trigger": [{"platform": "event", "event_type": "volcano_continue"}]},
                    {"event": "volcano_finished", "event_data": {"name": name}},
                ],
            }
        )
    assert await async_setup_component(hass, "automation", {"automation": config})
    await drain()
    component = hass.data["automation"]
    return (
        component.get_entity("automation.volcano_selected"),
        component.get_entity("automation.volcano_unrelated"),
    )


async def wait_runs(entity, count):
    ready = asyncio.Event()

    @callback
    def changed(event):
        if entity.action_script.runs == count:
            ready.set()

    remove = entity.hass.bus.async_listen(EVENT_STATE_CHANGED, changed)
    try:
        if entity.action_script.runs == count:
            ready.set()
        async with asyncio.timeout(2):
            await ready.wait()
        await drain()
    finally:
        remove()


async def stop(hass, targets, context=None):
    await hass.services.async_call(
        DOMAIN,
        SERVICE_STOP_AUTOMATION_RUNS,
        {"entity_id": targets},
        blocking=True,
        context=context,
    )


@pytest.mark.parametrize("mode", ["single", "restart", "queued", "parallel"])
async def test_stop_runs_preserves_enabled_state_and_future_triggers(hass, routines, mode):
    selected, unrelated = await load_automations(hass, mode)
    finished = []

    @callback
    def record(event):
        finished.append(event.data["name"])

    hass.bus.async_listen("volcano_finished", record)
    count = 3 if mode in ("queued", "parallel") else 1
    for run in range(count):
        hass.bus.async_fire("volcano_start_selected")
        await wait_runs(selected, run + 1)
    hass.bus.async_fire("volcano_start_unrelated")
    await wait_runs(unrelated, 1)
    await drain()

    await stop(hass, selected.entity_id)
    await drain()
    assert selected.action_script.runs == 0
    assert hass.states.get(selected.entity_id).state == "on"
    assert hass.states.get(selected.entity_id).attributes["current"] == 0
    assert unrelated.action_script.runs == 1

    hass.bus.async_fire("volcano_continue")
    await drain()
    assert finished == ["unrelated"]
    # A fresh event must still start the automation, proving its triggers stayed attached.
    hass.bus.async_fire("volcano_start_selected")
    await wait_runs(selected, 1)
    await drain()
    hass.bus.async_fire("volcano_continue")
    await drain()
    assert finished == ["unrelated", "selected"]


async def test_stop_does_not_enable_a_disabled_automation_with_a_manual_run(hass, routines):
    selected, _ = await load_automations(hass, enabled=False)
    trigger = asyncio.create_task(
        hass.services.async_call(
            "automation", "trigger", {"entity_id": selected.entity_id}, blocking=True
        )
    )
    await wait_runs(selected, 1)
    await stop(hass, selected.entity_id)
    await trigger
    await drain()
    assert selected.action_script.runs == 0
    assert hass.states.get(selected.entity_id).state == "off"
    hass.bus.async_fire("volcano_start_selected")
    await drain()
    assert selected.action_script.runs == 0


async def test_idle_and_duplicate_targets_are_harmless(hass, routines):
    selected, unrelated = await load_automations(hass)
    await stop(hass, [selected.entity_id, selected.entity_id, unrelated.entity_id])
    assert hass.states.get(selected.entity_id).state == "on"
    assert hass.states.get(unrelated.entity_id).state == "on"
    assert selected.action_script.runs == unrelated.action_script.runs == 0


@pytest.mark.parametrize(
    "targets", [None, [], "all", "script.example", ["automation.ok", "light.no"]]
)
def test_stop_requires_explicit_automation_ids(targets):
    with pytest.raises(vol.Invalid):
        STOP_AUTOMATION_RUNS_SCHEMA({"entity_id": targets} if targets is not None else {})


async def test_missing_target_is_reported_without_stopping_other_targets(hass, routines):
    selected, _ = await load_automations(hass)
    hass.bus.async_fire("volcano_start_selected")
    await wait_runs(selected, 1)
    with pytest.raises(ServiceValidationError, match="not available"):
        await stop(hass, [selected.entity_id, "automation.missing"])
    assert selected.action_script.runs == 1
    await selected.action_script.async_stop()


@pytest.mark.parametrize("kind", ["unknown", "inactive", "read_only", "other_entity"])
async def test_stop_checks_control_permission_for_every_target(hass, routines, kind):
    selected, unrelated = await load_automations(hass)
    hass.bus.async_fire("volcano_start_selected")
    await wait_runs(selected, 1)
    user_id = "deleted-user"
    if kind != "unknown":
        user = MockUser(is_active=kind != "inactive").add_to_hass(hass)
        policy = {CAT_ENTITIES: True}
        if kind == "read_only":
            policy = {CAT_ENTITIES: {"all": {"read": True}}}
        elif kind == "other_entity":
            policy = {CAT_ENTITIES: {"entity_ids": {selected.entity_id: {POLICY_CONTROL: True}}}}
        user.mock_policy(policy)
        user_id = user.id
    with pytest.raises(UnknownUser if kind == "unknown" else Unauthorized):
        await stop(hass, [selected.entity_id, unrelated.entity_id], Context(user_id=user_id))
    assert selected.action_script.runs == 1
    await selected.action_script.async_stop()


async def test_authorized_entity_permission_can_stop_runs(hass, routines):
    selected, _ = await load_automations(hass)
    user = MockUser().add_to_hass(hass)
    user.mock_policy({CAT_ENTITIES: {"entity_ids": {selected.entity_id: {POLICY_CONTROL: True}}}})
    hass.bus.async_fire("volcano_start_selected")
    await wait_runs(selected, 1)
    await stop(hass, selected.entity_id, Context(user_id=user.id))
    assert selected.action_script.runs == 0
    assert hass.states.get(selected.entity_id).state == "on"


async def test_batch_cancellation_attempts_remaining_runs_after_a_failure(hass, routines):
    selected, unrelated = await load_automations(hass)
    for name, entity in [("selected", selected), ("unrelated", unrelated)]:
        hass.bus.async_fire(f"volcano_start_{name}")
        await wait_runs(entity, 1)
    with patch.object(
        selected.action_script, "async_stop", side_effect=HomeAssistantError("Failed")
    ):
        with pytest.raises(HomeAssistantError, match="Could not stop automation runs"):
            await stop(hass, [selected.entity_id, unrelated.entity_id])
    assert unrelated.action_script.runs == 0
    assert hass.states.get(unrelated.entity_id).state == "on"
    await selected.action_script.async_stop()


async def test_unsupported_automation_never_falls_back_to_disabling_it(hass, routines):
    selected, _ = await load_automations(hass)
    with patch.object(selected.action_script, "async_stop", None):
        with pytest.raises(ServiceValidationError, match="without disabling.*not supported"):
            await stop(hass, selected.entity_id)
    assert hass.states.get(selected.entity_id).state == "on"
