"""Api hub and integration data."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from aiohttp import ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from pyintradel.api import get_data

from .const import (
    CONF_ANNUAL_FEE,
    CONF_COOKIE,
    CONF_HOUSEHOLD_SIZE,
    CONF_PRICE_ORGANIC_KG,
    CONF_PRICE_RESIDUAL_KG,
    CONF_QUOTA_ORGANIC_KG,
    CONF_QUOTA_RESIDUAL_KG,
    CURRENCY,
    DEFAULT_ANNUAL_FEE,
    DEFAULT_HOUSEHOLD_SIZE,
    DEFAULT_PRICE_ORGANIC_KG,
    DEFAULT_PRICE_RESIDUAL_KG,
    DEFAULT_QUOTA_ORGANIC_KG,
    DEFAULT_QUOTA_RESIDUAL_KG,
    DOMAIN,
)
from .model import Account, parse_account
from .tariff import Tariff, build_tariff

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
        # Parsed view of the last payload. Entities read this instead of the raw
        # dicts; it is refreshed on every poll.
        self.account: Account = Account(year=dt_util.now().year, bins=(), recyparc=None)

    @property
    def tariff(self) -> Tariff:
        """Build the tariff from the entry options.

        Read on access rather than cached: the options flow reloads the entry,
        but this keeps the tariff correct even if that ever changes.
        """
        options = self.config_entry.options
        return build_tariff(
            household_size=options.get(CONF_HOUSEHOLD_SIZE, DEFAULT_HOUSEHOLD_SIZE),
            quota_organic_kg=options.get(CONF_QUOTA_ORGANIC_KG, DEFAULT_QUOTA_ORGANIC_KG),
            quota_residual_kg=options.get(CONF_QUOTA_RESIDUAL_KG, DEFAULT_QUOTA_RESIDUAL_KG),
            price_organic_per_kg=options.get(CONF_PRICE_ORGANIC_KG, DEFAULT_PRICE_ORGANIC_KG),
            price_residual_per_kg=options.get(CONF_PRICE_RESIDUAL_KG, DEFAULT_PRICE_RESIDUAL_KG),
            annual_fee=options.get(CONF_ANNUAL_FEE, DEFAULT_ANNUAL_FEE),
            currency=CURRENCY,
        )

    @property
    def session(self) -> ClientSession:
        """The coordinator's own aiohttp session, reused by the keep-alive."""
        return self._session

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch data from intradel."""
        # Intradel re-authenticates on every request, so no cookie should survive
        # from one poll to the next: start each poll from a clean jar.
        self._session.cookie_jar.clear()
        cookie = self.config_entry.data.get(CONF_COOKIE)
        if not cookie:
            # An entry created before the login/password method was removed. That
            # method can no longer authenticate (the site verifies an invisible
            # reCAPTCHA server-side), so ask for a session cookie instead.
            raise ConfigEntryAuthFailed(
                "Intradel now requires a session cookie; please re-authenticate"
            )
        try:
            # pyintradel types its return as list[Any]; narrow it for consumers.
            data: list[dict[str, Any]] = await get_data(self._session, cookie=cookie)
        except ValueError as err:
            message = str(err.args[0]) if err.args else str(err)
            # pyintradel signals bad credentials (or a rejected/expired cookie)
            # with this specific message; anything else is an unexpected-markup
            # / transient scraping error.
            if "login/password" in message:
                raise ConfigEntryAuthFailed(message) from err
            raise UpdateFailed(message) from err

        self.account = parse_account(data, default_year=dt_util.now().year)
        return data
