"""The Intradel integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_COOKIE,
    CONF_KEEPALIVE_INTERVAL,
    DEFAULT_KEEPALIVE_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    PLATFORMS,
)
from .coordinator import IntradelConfigEntry, IntradelCoordinator
from .keepalive import ping_session

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: IntradelConfigEntry) -> bool:
    """Set up intradel from a config entry."""
    scan_interval = timedelta(minutes=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    coordinator = IntradelCoordinator(hass, entry, scan_interval)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _async_setup_keepalive(hass, entry, coordinator)

    return True


def _async_setup_keepalive(
    hass: HomeAssistant, entry: IntradelConfigEntry, coordinator: IntradelCoordinator
) -> None:
    """Ping the site often enough that the session cookie never goes stale.

    The server drops the session after a period of inactivity much shorter than the
    poll interval. Skipped when the interval is set to 0.
    """
    cookie = entry.data.get(CONF_COOKIE)
    minutes = entry.options.get(CONF_KEEPALIVE_INTERVAL, DEFAULT_KEEPALIVE_INTERVAL)
    if not cookie or not minutes:
        return

    async def _async_ping(_now: object) -> None:
        if not await ping_session(coordinator.session, cookie):
            # The next poll turns this into a re-authentication flow; logging it
            # here explains why the entry is about to ask for a fresh cookie.
            _LOGGER.info("Intradel session expired despite keep-alive")

    entry.async_on_unload(async_track_time_interval(hass, _async_ping, timedelta(minutes=minutes)))


async def _async_update_listener(hass: HomeAssistant, entry: IntradelConfigEntry) -> None:
    """Reload the entry when its options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: IntradelConfigEntry) -> bool:
    """Unload a config entry."""
    # The coordinator's aiohttp session is auto-detached by HA on unload.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
