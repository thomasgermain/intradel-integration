"""Config flow for intradel integration."""

from __future__ import annotations

import logging
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

from .const import CONF_TOWN, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_TOWN): vol.All(vol.Coerce(str), vol.In(TOWNS_MAP.keys())),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate the user input allows us to connect.

    Data has the keys from DATA_SCHEMA with values provided by the user.
    """
    await validate_authentication(hass, data[CONF_USERNAME], data[CONF_PASSWORD], data[CONF_TOWN])

    return {"title": "Intradel"}


async def validate_authentication(
    hass: HomeAssistant, username: str, password: str, town: str
) -> None:
    """Ensure provided credentials are working."""
    # One-shot validation: the shared HA session is the documented tool here; the
    # actual polling uses the coordinator's own isolated session.
    try:
        if not await get_data(async_get_clientsession(hass), username, password, town):
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
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                return self.async_create_entry(title=info["title"], data=user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)


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
