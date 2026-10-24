"""Config flow for intradel integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from pyintradel.api import AuthenticationError, IntradelError, get_data

from .const import (
    CONF_COOKIE,
    CONF_KEEPALIVE_INTERVAL,
    DEFAULT_KEEPALIVE_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_KEEPALIVE_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    REQUEST_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

# A live session token: masked like a password.
DATA_SCHEMA_COOKIE = vol.Schema(
    {vol.Required(CONF_COOKIE): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
)

INTRADEL_URL = "https://www.intradel.be/particulier/"


async def validate_authentication(hass: HomeAssistant, cookie: str) -> None:
    """Ensure the provided session cookie is working."""
    # One-shot validation: the shared HA session is the documented tool here; the
    # actual polling uses the coordinator's own isolated session.

    session = async_get_clientsession(hass)

    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            # Any payload, even an empty one, means the cookie was accepted.
            await get_data(session, cookie=cookie)
    except AuthenticationError as err:
        _LOGGER.debug("Unable to authenticate: %s", err)
        raise InvalidAuth from err
    # pyintradel does not wrap transport errors, only its own IntradelError family.
    except (IntradelError, aiohttp.ClientError, TimeoutError) as err:
        _LOGGER.debug("Unable to fetch intradel data: %s", err)
        raise CannotConnect from err


def _minutes(minimum: int, maximum: int) -> vol.All:
    """A whole number of minutes within bounds (the selector yields a float)."""
    selector = NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="min",
        )
    )
    return vol.All(selector, vol.Coerce(int))


class IntradelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Intradel."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> IntradelOptionsFlowHandler:
        """Get the options flow for this handler."""
        return IntradelOptionsFlowHandler()

    async def _async_cookie_form(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Ask for a session cookie and validate it.

        Shared by the initial setup and the re-authentication, which differ only
        in whether they create an entry or update the existing one.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await validate_authentication(self.hass, user_input[CONF_COOKIE])
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                data = {CONF_COOKIE: user_input[CONF_COOKIE]}
                if self.source == SOURCE_REAUTH:
                    # Full replace, not data_updates: drops the leftover
                    # login/password/town of an entry created before the
                    # login/password method was removed.
                    return self.async_update_reload_and_abort(self._get_reauth_entry(), data=data)
                return self.async_create_entry(title="Intradel", data=data)

        return self.async_show_form(
            step_id=step_id,
            data_schema=DATA_SCHEMA_COOKIE,
            errors=errors,
            description_placeholders={"intradel_url": INTRADEL_URL},
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle authentication with a session cookie."""
        return await self._async_cookie_form("user", user_input)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Handle re-authentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm re-authentication with a fresh session cookie."""
        return await self._async_cookie_form("reauth_confirm", user_input)


class IntradelOptionsFlowHandler(OptionsFlowWithReload):
    """Handle an option flow; the entry reloads itself when its options change."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): _minutes(MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL),
                vol.Optional(
                    CONF_KEEPALIVE_INTERVAL,
                    default=options.get(CONF_KEEPALIVE_INTERVAL, DEFAULT_KEEPALIVE_INTERVAL),
                ): _minutes(0, MAX_KEEPALIVE_INTERVAL),
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
