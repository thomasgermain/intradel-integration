"""Config flow for intradel integration."""

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
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pyintradel.api import get_data
from pyintradel.api.towns import TOWNS_MAP

from .const import CONF_COOKIE, CONF_TOWN, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA_LOGIN = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_TOWN): vol.All(vol.Coerce(str), vol.In(TOWNS_MAP.keys())),
    }
)

DATA_SCHEMA_COOKIE = vol.Schema({vol.Required(CONF_COOKIE): str})


async def validate_authentication(
    hass: HomeAssistant,
    username: str | None = None,
    password: str | None = None,
    town: str | None = None,
    cookie: str | None = None,
) -> None:
    """Ensure the provided credentials (or cookie) are working."""
    # One-shot validation: the shared HA session is the documented tool here; the
    # actual polling uses the coordinator's own isolated session.
    try:
        if not await get_data(
            async_get_clientsession(hass), username, password, town, cookie=cookie
        ):
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

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Let the user pick between login/password and a session cookie.

        The login form is now gated behind an invisible reCAPTCHA that plain
        login/password requests can be rejected by, so a session cookie captured
        from an already logged-in browser is offered as an alternative.
        """
        return self.async_show_menu(step_id="user", menu_options=["login", "cookie"])

    async def async_step_login(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle authentication with login/password/town."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await validate_authentication(
                    self.hass,
                    username=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                    town=user_input[CONF_TOWN],
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title="Intradel", data=user_input)

        return self.async_show_form(step_id="login", data_schema=DATA_SCHEMA_LOGIN, errors=errors)

    async def async_step_cookie(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle authentication with a session cookie."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await validate_authentication(self.hass, cookie=user_input[CONF_COOKIE])
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title="Intradel", data=user_input)

        return self.async_show_form(step_id="cookie", data_schema=DATA_SCHEMA_COOKIE, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Handle re-authentication: let the user pick login or cookie.

        Offered regardless of which method the entry originally used, so a user
        stuck on a reCAPTCHA-rejected login/password can switch to a cookie (or
        back) without deleting and re-adding the integration.
        """
        return self.async_show_menu(
            step_id="reauth", menu_options=["reauth_confirm", "reauth_cookie"]
        )

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm re-authentication with login/password/town.

        The town is reused (and not asked again) if the entry already has one;
        switching from a cookie-based entry asks for it since none is known yet.
        """
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        known_town = reauth_entry.data.get(CONF_TOWN)

        if user_input is not None:
            town = known_town or user_input[CONF_TOWN]
            try:
                await validate_authentication(
                    self.hass,
                    username=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                    town=town,
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Full replace (not data_updates): drops a leftover cookie when
                # switching from a cookie-based entry.
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_TOWN: town,
                    },
                )

        if known_town:
            schema = vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME, default=reauth_entry.data.get(CONF_USERNAME, "")
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            )
        else:
            schema = DATA_SCHEMA_LOGIN

        return self.async_show_form(step_id="reauth_confirm", data_schema=schema, errors=errors)

    async def async_step_reauth_cookie(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm re-authentication with a fresh session cookie."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                await validate_authentication(self.hass, cookie=user_input[CONF_COOKIE])
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Full replace (not data_updates): drops leftover login/password/town
                # when switching from a login-based entry.
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={CONF_COOKIE: user_input[CONF_COOKIE]},
                )

        return self.async_show_form(
            step_id="reauth_cookie",
            data_schema=DATA_SCHEMA_COOKIE,
            errors=errors,
        )


class IntradelOptionsFlowHandler(OptionsFlow):
    """Handle an option flow."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): cv.positive_int
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
