"""Diagnostics support for the Intradel integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import IntradelConfigEntry

# Credentials in the entry data, and the chip number ("id") in the scraped data.
TO_REDACT_ENTRY = {CONF_USERNAME, CONF_PASSWORD}
TO_REDACT_DATA = {"id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: IntradelConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {
        "entry_data": async_redact_data(entry.data, TO_REDACT_ENTRY),
        "data": async_redact_data(entry.runtime_data.data, TO_REDACT_DATA),
    }
