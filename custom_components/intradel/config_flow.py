"""Config flow for intradel integration.

The Intradel login form is gated behind an invisible reCAPTCHA that the site
verifies server-side: a login/password/town request without a challenge token is
always rejected ("La verification anti-spam a echoue"), so that authentication
method is not offered at all. The only usable credential is a session cookie
captured from a browser that is already logged in.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pyintradel.api import get_data

from .const import (
    CONF_COOKIE,
    CONF_HOUSEHOLD_SIZE,
    CONF_KEEPALIVE_INTERVAL,
    CONF_MAX_COLLECTIONS,
    CONF_QUOTA_ORGANIC_KG,
    CONF_QUOTA_RESIDUAL_KG,
    DEFAULT_HOUSEHOLD_SIZE,
    DEFAULT_KEEPALIVE_INTERVAL,
    DEFAULT_MAX_COLLECTIONS,
    DEFAULT_QUOTA_ORGANIC_KG,
    DEFAULT_QUOTA_RESIDUAL_KG,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA_COOKIE = vol.Schema({vol.Required(CONF_COOKIE): str})

INTRADEL_URL = "https://www.intradel.be/particulier/"


async def validate_authentication(hass: HomeAssistant, cookie: str) -> None:
    """Ensure the provided session cookie is working."""
    # One-shot validation: the shared HA session is the documented tool here; the
    # actual polling uses the coordinator's own isolated session.
    try:
        if not await get_data(async_get_clientsession(hass), cookie=cookie):
            raise InvalidAuth
    except ValueError as err:
        _LOGGER.error("Unable to authenticate: %s", err)
        raise InvalidAuth from err


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
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                data = {CONF_COOKIE: user_input[CONF_COOKIE]}
                if self.source == "reauth":
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


class IntradelOptionsFlowHandler(OptionsFlow):
    """Handle an option flow."""

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
                ): cv.positive_int,
                vol.Optional(
                    CONF_KEEPALIVE_INTERVAL,
                    default=options.get(CONF_KEEPALIVE_INTERVAL, DEFAULT_KEEPALIVE_INTERVAL),
                ): cv.positive_int,
                # Quotas and household size drive the cost and quota sensors.
                # They are town- and household-specific, hence configurable.
                vol.Optional(
                    CONF_HOUSEHOLD_SIZE,
                    default=options.get(CONF_HOUSEHOLD_SIZE, DEFAULT_HOUSEHOLD_SIZE),
                ): vol.All(cv.positive_int, vol.Range(min=1)),
                vol.Optional(
                    CONF_QUOTA_ORGANIC_KG,
                    default=options.get(CONF_QUOTA_ORGANIC_KG, DEFAULT_QUOTA_ORGANIC_KG),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_QUOTA_RESIDUAL_KG,
                    default=options.get(CONF_QUOTA_RESIDUAL_KG, DEFAULT_QUOTA_RESIDUAL_KG),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_MAX_COLLECTIONS,
                    default=options.get(CONF_MAX_COLLECTIONS, DEFAULT_MAX_COLLECTIONS),
                ): cv.positive_int,
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
