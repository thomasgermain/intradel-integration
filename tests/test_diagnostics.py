"""Test the Intradel diagnostics."""

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intradel.const import CONF_COOKIE
from custom_components.intradel.diagnostics import async_get_config_entry_diagnostics

REDACTED = "**REDACTED**"


async def test_diagnostics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """The session cookie and chip ids are redacted, the payload is preserved."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    # The cookie is a live session token, at least as sensitive as a password.
    assert diag["entry_data"][CONF_COOKIE] == REDACTED

    assert all(item["id"] == REDACTED for item in diag["data"])
    assert diag["data"][0]["total"] == "61"
    assert diag["data"][0]["name"] == "ORGANIQUE"
