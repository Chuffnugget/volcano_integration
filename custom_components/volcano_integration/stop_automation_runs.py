"""Cancel automation runs without changing their enabled state or triggers."""

import asyncio

import voluptuous as vol
from homeassistant.auth.permissions.const import CAT_ENTITIES, POLICY_CONTROL
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
    Unauthorized,
    UnknownUser,
)
from homeassistant.helpers import config_validation as cv

SERVICE_STOP_AUTOMATION_RUNS = "stop_automation_runs"
STOP_AUTOMATION_RUNS_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): vol.All(
            cv.entity_ids, vol.Length(min=1), [vol.Match(r"^automation\.")]
        )
    }
)


async def async_stop_automation_runs(hass: HomeAssistant, call: ServiceCall) -> None:
    """Stop current runs only, with control permission for every explicit target."""
    entity_ids = list(dict.fromkeys(call.data["entity_id"]))
    if call.context.user_id is not None:
        user = await hass.auth.async_get_user(call.context.user_id)
        if user is None:
            raise UnknownUser(context=call.context, permission=POLICY_CONTROL)
        for entity_id in entity_ids:
            if not user.is_active or not user.permissions.check_entity(entity_id, POLICY_CONTROL):
                raise Unauthorized(
                    context=call.context,
                    entity_id=entity_id,
                    perm_category=CAT_ENTITIES,
                    permission=POLICY_CONTROL,
                )

    # Automation has no stop-only service. Use the same Script cancellation API
    # as HA's turn_off action, without disabling the entity or removing triggers.
    component = hass.data.get("automation")
    scripts = []
    for entity_id in entity_ids:
        entity = component.get_entity(entity_id) if component is not None else None
        state = hass.states.get(entity_id)
        if entity is None or state is None or state.state == "unavailable":
            raise ServiceValidationError(f"Automation {entity_id} is not available")
        script = getattr(entity, "action_script", None)
        if not callable(getattr(script, "async_stop", None)):
            raise ServiceValidationError(
                f"Stopping runs without disabling {entity_id} is not supported"
            )
        scripts.append(script)

    results = await asyncio.gather(
        *(script.async_stop() for script in scripts), return_exceptions=True
    )
    errors = [
        f"{entity_id}: {result}"
        for entity_id, result in zip(entity_ids, results, strict=True)
        if isinstance(result, Exception)
    ]
    if errors:
        raise HomeAssistantError("Could not stop automation runs: " + "; ".join(errors))
