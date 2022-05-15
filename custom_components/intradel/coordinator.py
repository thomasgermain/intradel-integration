"""Api hub and integration data."""
from __future__ import annotations

import logging
from datetime import timedelta


from .const import CONF_TOWN
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from pyintradel.api import get_data

_LOGGER = logging.getLogger(__name__)


class IntradelCoordinator(DataUpdateCoordinator):
    """Intradel coordinator."""

    def __init__(
        self,
        hass,
        name,
        update_interval: timedelta | None,
    ):
        """Init."""

        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=update_interval,
            update_method=self._fetch_data,
        )
        self._username = self.config_entry.data[CONF_USERNAME]
        self._password = self.config_entry.data[CONF_PASSWORD]
        self._town = self.config_entry.data[CONF_TOWN]

    async def _fetch_data(self):
        return await get_data(
            async_get_clientsession(self.hass),
            self._username,
            self._password,
            self._town,
        )
