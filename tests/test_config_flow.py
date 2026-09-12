"""Test the Intradel config flow.

Only a session cookie can authenticate: the login form is gated behind a
reCAPTCHA the site verifies server-side, so no login/password step exists.
"""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intradel.const import (
    CONF_COOKIE,
    CONF_KEEPALIVE_INTERVAL,
    DEFAULT_KEEPALIVE_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

from .const import COOKIE_INPUT, SAMPLE_DATA


async def test_user_flow_asks_for_a_cookie(hass: HomeAssistant) -> None:
    """The flow goes straight to the cookie form, with no method to choose."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_user_flow_success(hass: HomeAssistant) -> None:
    """A valid cookie creates the entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    with patch(
        "custom_components.intradel.config_flow.get_data",
        new_callable=AsyncMock,
        return_value=SAMPLE_DATA,
    ) as mock:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], COOKIE_INPUT)
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Intradel"
    assert result["data"] == COOKIE_INPUT
    # The cookie is passed as a keyword argument, never as login/password.
    assert mock.call_args.kwargs["cookie"] == COOKIE_INPUT[CONF_COOKIE]


@pytest.mark.parametrize(
    ("side_effect", "return_value", "expected"),
    [
        (ValueError("login/password seems incorrect"), None, "invalid_auth"),
        (None, [], "invalid_auth"),
        (RuntimeError("boom"), None, "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    side_effect: Exception | None,
    return_value: list[dict[str, str]] | None,
    expected: str,
) -> None:
    """A rejected cookie keeps the form open with an error."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    with patch(
        "custom_components.intradel.config_flow.get_data",
        new_callable=AsyncMock,
        side_effect=side_effect,
        return_value=return_value,
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], COOKIE_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": expected}


async def test_single_instance_allowed(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Only one entry can exist."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_reauth_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_get_data: AsyncMock
) -> None:
    """Re-authentication replaces the stored cookie."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.intradel.config_flow.get_data",
        new_callable=AsyncMock,
        return_value=SAMPLE_DATA,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_COOKIE: "PHPSESSID=fresh"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_COOKIE] == "PHPSESSID=fresh"


async def test_reauth_flow_invalid_auth(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """A rejected cookie leaves the stored one untouched."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)

    with patch(
        "custom_components.intradel.config_flow.get_data",
        new_callable=AsyncMock,
        side_effect=ValueError("login/password seems incorrect"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_COOKIE: "PHPSESSID=stale"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert mock_config_entry.data == COOKIE_INPUT


async def test_reauth_replaces_legacy_credentials(
    hass: HomeAssistant, mock_legacy_config_entry: MockConfigEntry, mock_get_data: AsyncMock
) -> None:
    """An entry predating the removal loses its username, password and town."""
    mock_legacy_config_entry.add_to_hass(hass)
    result = await mock_legacy_config_entry.start_reauth_flow(hass)

    with patch(
        "custom_components.intradel.config_flow.get_data",
        new_callable=AsyncMock,
        return_value=SAMPLE_DATA,
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], COOKIE_INPUT)
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    # A full replace, so nothing of the old credentials survives.
    assert mock_legacy_config_entry.data == COOKIE_INPUT


async def test_options_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_get_data: AsyncMock
) -> None:
    """The options flow updates the scan and keep-alive intervals."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    user_input = {
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL + 5,
        CONF_KEEPALIVE_INTERVAL: 10,
    }
    result = await hass.config_entries.options.async_configure(result["flow_id"], user_input)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == user_input


async def test_options_flow_defaults(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_get_data: AsyncMock
) -> None:
    """The scan and keep-alive intervals keep their documented defaults."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    schema = result["data_schema"]({})

    assert schema[CONF_SCAN_INTERVAL] == DEFAULT_SCAN_INTERVAL
    assert schema[CONF_KEEPALIVE_INTERVAL] == DEFAULT_KEEPALIVE_INTERVAL
