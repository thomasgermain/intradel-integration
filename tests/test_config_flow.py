"""Test the Intradel config and options flow."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intradel.const import CONF_TOWN, DEFAULT_SCAN_INTERVAL, DOMAIN

from .const import SAMPLE_DATA, USER_INPUT


async def test_user_flow_success(hass: HomeAssistant) -> None:
    """A valid login creates the config entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    with (
        patch(
            "custom_components.intradel.config_flow.get_data",
            new_callable=AsyncMock,
            return_value=SAMPLE_DATA,
        ),
        patch(
            "custom_components.intradel.async_setup_entry",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_setup_entry,
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Intradel"
    assert result["data"] == USER_INPUT
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(
    ("side_effect", "return_value", "expected_error"),
    [
        (None, [], "invalid_auth"),
        (ValueError("Town not found"), None, "invalid_auth"),
        (Exception("boom"), None, "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    side_effect: Exception | None,
    return_value: list | None,
    expected_error: str,
) -> None:
    """Authentication failures keep the form open with the right error."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    with patch(
        "custom_components.intradel.config_flow.get_data",
        new_callable=AsyncMock,
        side_effect=side_effect,
        return_value=return_value,
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}


async def test_single_instance_allowed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A second config entry is rejected (single_config_entry in manifest)."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """The options flow updates the scan interval."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL + 5}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL + 5}


async def test_reauth_flow(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Re-authentication updates the credentials and keeps the town."""
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
            result["flow_id"],
            {CONF_USERNAME: "new-user", CONF_PASSWORD: "new-secret"},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_USERNAME] == "new-user"
    assert mock_config_entry.data[CONF_PASSWORD] == "new-secret"
    # The town is not asked again and must be preserved.
    assert mock_config_entry.data[CONF_TOWN] == USER_INPUT[CONF_TOWN]


async def test_reauth_flow_invalid_auth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Wrong credentials during reauth keep the form open with an error."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reauth_flow(hass)

    with patch(
        "custom_components.intradel.config_flow.get_data",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "new-user", CONF_PASSWORD: "bad"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
