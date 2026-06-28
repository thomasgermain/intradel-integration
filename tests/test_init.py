"""Test the Intradel integration setup and unload."""

from unittest.mock import AsyncMock

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intradel.coordinator import IntradelCoordinator


async def test_setup_and_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """A config entry sets up, exposes its coordinator, and unloads cleanly."""
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert isinstance(mock_config_entry.runtime_data, IntradelCoordinator)
    assert mock_get_data.call_count == 1

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retry_on_fetch_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """A failure during the first refresh puts the entry in retry state."""
    mock_get_data.side_effect = ValueError("Wrong response received")
    mock_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_auth_failure_triggers_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """A credentials error starts a reauth flow instead of an endless retry."""
    mock_get_data.side_effect = ValueError(
        "Wrong response received, login/password seems incorrect"
    )
    mock_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(flow["context"]["source"] == SOURCE_REAUTH for flow in flows)
