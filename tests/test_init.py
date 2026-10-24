"""Test the Intradel integration setup and unload."""

import copy
from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from pyintradel.api import ApiError, AuthenticationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intradel.coordinator import IntradelCoordinator

from .const import SAMPLE_DATA


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
    mock_get_data.side_effect = ApiError(503)
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
    mock_get_data.side_effect = AuthenticationError()
    mock_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(flow["context"]["source"] == SOURCE_REAUTH for flow in flows)


async def test_legacy_entry_without_cookie_triggers_reauth(
    hass: HomeAssistant,
    mock_legacy_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """An entry predating the removal of login/password asks for a cookie.

    Such an entry cannot authenticate at all any more, so it must fail loudly
    into a reauth flow rather than hitting the site with credentials the
    reCAPTCHA will reject.
    """
    mock_legacy_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(mock_legacy_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_legacy_config_entry.state is ConfigEntryState.SETUP_ERROR
    # The site is never contacted: there is no usable credential to try.
    assert mock_get_data.call_count == 0
    flows = hass.config_entries.flow.async_progress()
    assert any(flow["context"]["source"] == SOURCE_REAUTH for flow in flows)


async def test_listeners_are_notified_only_when_the_data_changes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """An identical payload must not rewrite every sensor state."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = mock_config_entry.runtime_data
    notified = MagicMock()
    coordinator.async_add_listener(notified)

    mock_get_data.return_value = copy.deepcopy(SAMPLE_DATA)
    await coordinator.async_refresh()
    notified.assert_not_called()

    changed = copy.deepcopy(SAMPLE_DATA)
    changed[0]["total"] = "99"
    mock_get_data.return_value = changed
    await coordinator.async_refresh()
    notified.assert_called_once()
