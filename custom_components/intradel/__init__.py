"""The Intradel integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant

from .const import DEFAULT_SCAN_INTERVAL, PLATFORMS
from .coordinator import IntradelConfigEntry, IntradelCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: IntradelConfigEntry) -> bool:
    """Set up intradel from a config entry."""
    scan_interval = timedelta(
        minutes=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    coordinator = IntradelCoordinator(hass, entry, scan_interval)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: IntradelConfigEntry
) -> None:
    """Reload the entry when its options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: IntradelConfigEntry) -> bool:
    """Unload a config entry."""
    # The coordinator's aiohttp session is auto-detached by HA on unload.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
