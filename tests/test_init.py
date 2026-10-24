"""Test the Intradel integration setup and unload."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pyintradel.api import ApiError, AuthenticationError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.intradel.const import DEFAULT_KEEPALIVE_INTERVAL
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
    mock_get_data.side_effect = ApiError(503)
    mock_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_retry_on_timeout(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """A site that does not answer in time is retried, not treated as a bad cookie."""

    async def _hang(*args: object, **kwargs: object) -> None:
        await asyncio.sleep(3600)

    mock_get_data.side_effect = _hang
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.intradel.coordinator.REQUEST_TIMEOUT", 0.01):
        assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert not hass.config_entries.flow.async_progress()


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


async def _fire_keepalive(hass: HomeAssistant) -> None:
    """Advance time past one keep-alive interval and let the ping run."""
    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(minutes=DEFAULT_KEEPALIVE_INTERVAL, seconds=1)
    )
    await hass.async_block_till_done()


async def test_keepalive_expiry_starts_reauth_without_waiting_for_a_poll(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """A dead session found by the ping asks for a fresh cookie right away."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.config_entries.flow.async_progress()

    with patch(
        "custom_components.intradel.ping_session", new_callable=AsyncMock, return_value=False
    ) as ping:
        await _fire_keepalive(hass)
        await _fire_keepalive(hass)

    assert ping.call_count == 2
    # The poll interval (12 h) has not elapsed: only the ping can have started this.
    assert mock_get_data.call_count == 1
    flows = hass.config_entries.flow.async_progress()
    # The second failed ping must not open a second flow.
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


async def test_keepalive_live_session_does_not_start_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """A valid session is left alone."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    with patch(
        "custom_components.intradel.ping_session", new_callable=AsyncMock, return_value=True
    ) as ping:
        await _fire_keepalive(hass)

    assert ping.call_count == 1
    assert not hass.config_entries.flow.async_progress()
