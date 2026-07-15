"""Api hub and integration data."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pyintradel.api import get_data

from .const import CONF_COOKIE, CONF_TOWN, DOMAIN

_LOGGER = logging.getLogger(__name__)

type IntradelConfigEntry = ConfigEntry[IntradelCoordinator]


class IntradelCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Intradel coordinator."""

    config_entry: IntradelConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: IntradelConfigEntry,
        update_interval: timedelta,
    ) -> None:
        """Init."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=update_interval,
        )
        # Dedicated session: its own (isolated) cookie jar avoids sharing the
        # Intradel login cookie with the global HA session, while reusing HA's
        # shared connector. Created during entry setup, so HA auto-detaches it on
        # unload (and on setup-failure cleanup) -- we must not close it ourselves.
        self._session = async_create_clientsession(hass)

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch data from intradel."""
        # Intradel re-authenticates on every request, so no cookie should survive
        # from one poll to the next: start each poll from a clean jar.
        self._session.cookie_jar.clear()
        entry_data = self.config_entry.data
        try:
            # pyintradel types its return as list[Any]; narrow it for consumers.
            if CONF_COOKIE in entry_data:
                data: list[dict[str, Any]] = await get_data(
                    self._session, cookie=entry_data[CONF_COOKIE]
                )
            else:
                data = await get_data(
                    self._session,
                    entry_data[CONF_USERNAME],
                    entry_data[CONF_PASSWORD],
                    entry_data[CONF_TOWN],
                )
        except ValueError as err:
            message = str(err.args[0]) if err.args else str(err)
            # pyintradel signals bad credentials (or a rejected/expired cookie)
            # with this specific message; anything else is an unexpected-markup
            # / transient scraping error.
            if "login/password" in message:
                raise ConfigEntryAuthFailed(message) from err
            raise UpdateFailed(message) from err
        return data
