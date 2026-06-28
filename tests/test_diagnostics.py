"""Test the Intradel diagnostics."""

from unittest.mock import AsyncMock

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intradel.const import CONF_TOWN
from custom_components.intradel.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .const import USER_INPUT

REDACTED = "**REDACTED**"


async def test_diagnostics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """Credentials and chip ids are redacted, payload is preserved."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert diag["entry_data"][CONF_USERNAME] == REDACTED
    assert diag["entry_data"][CONF_PASSWORD] == REDACTED
    assert diag["entry_data"][CONF_TOWN] == USER_INPUT[CONF_TOWN]

    assert all(item["id"] == REDACTED for item in diag["data"])
    assert diag["data"][0]["total"] == "61"
