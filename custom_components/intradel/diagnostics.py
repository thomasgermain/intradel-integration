"""Diagnostics support for the Intradel integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_COOKIE
from .coordinator import IntradelConfigEntry

# The cookie is a live session token and the only credential the integration
# still uses; username and password are redacted too because entries created
# before the login/password method was removed may still carry them.
TO_REDACT_ENTRY = {CONF_USERNAME, CONF_PASSWORD, CONF_COOKIE}
TO_REDACT_DATA = {"id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: IntradelConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {
        "entry_data": async_redact_data(entry.data, TO_REDACT_ENTRY),
        "data": async_redact_data(entry.runtime_data.data, TO_REDACT_DATA),
    }
