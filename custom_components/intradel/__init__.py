"""The Intradel integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_COOKIE,
    CONF_KEEPALIVE_INTERVAL,
    DEFAULT_KEEPALIVE_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
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
        if await ping_session(coordinator.session, cookie):
            return
        # Start the reauth now rather than at the next poll; a no-op if one is open.
        _LOGGER.debug("Intradel session expired despite keep-alive; starting reauthentication")
        entry.async_start_reauth(hass)

    entry.async_on_unload(async_track_time_interval(hass, _async_ping, timedelta(minutes=minutes)))


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: IntradelConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Allow deleting a device the site no longer reports (a stale bin)."""
    # Not set when the entry failed to load: nothing is reported then, so any device may go.
    coordinator: IntradelCoordinator | None = getattr(entry, "runtime_data", None)
    reported = {item["id"] for item in (coordinator.data if coordinator else None) or []}
    return not any(
        domain == DOMAIN and identifier in reported
        for domain, identifier in device_entry.identifiers
    )


async def async_unload_entry(hass: HomeAssistant, entry: IntradelConfigEntry) -> bool:
    """Unload a config entry."""
    # The coordinator's aiohttp session is auto-detached by HA on unload.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
