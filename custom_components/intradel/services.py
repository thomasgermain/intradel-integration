"""Services for the Intradel integration.

The login form is gated behind a server-verified invisible reCAPTCHA, so the
only usable credential is a session cookie obtained by logging in with a real
browser. Capturing it by hand through the browser's network inspector is the
documented way, and it is tedious.

`intradel.set_cookie` removes that tedium without touching the reCAPTCHA: the
user still authenticates on the website itself, in their own browser, and only
the resulting session is handed over. A one-click bookmarklet can call this
service, so refreshing the credential stops being a devtools exercise.
"""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import ATTR_COOKIE, CONF_COOKIE, DOMAIN, SERVICE_SET_COOKIE
from .coordinator import IntradelConfigEntry
from .keepalive import ping_session

_LOGGER = logging.getLogger(__name__)

SET_COOKIE_SCHEMA = vol.Schema({vol.Required(ATTR_COOKIE): cv.string})


def async_setup_services(hass: HomeAssistant, entry: IntradelConfigEntry) -> None:
    """Register the integration services.

    The integration allows a single config entry, so the service always targets
    that one entry and needs no target selector.
    """

    async def _async_set_cookie(call: ServiceCall) -> None:
        """Replace the stored session cookie with a freshly captured one."""
        cookie = call.data[ATTR_COOKIE].strip()
        if not cookie:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="empty_cookie")

        coordinator = entry.runtime_data
        if not await ping_session(coordinator.session, cookie):
            # Storing a cookie the site already rejects would only turn into a
            # failed poll and a re-authentication prompt; refuse it up front.
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_cookie"
            )

        # Full replace, not a merge: it drops any leftover login/password/town
        # from an entry that used to authenticate that way. Updating the entry
        # triggers the update listener, which reloads it.
        hass.config_entries.async_update_entry(entry, data={CONF_COOKIE: cookie})
        _LOGGER.info("Intradel session cookie updated")

    hass.services.async_register(
        DOMAIN, SERVICE_SET_COOKIE, _async_set_cookie, schema=SET_COOKIE_SCHEMA
    )


def async_unload_services(hass: HomeAssistant) -> None:
    """Remove the integration services."""
    hass.services.async_remove(DOMAIN, SERVICE_SET_COOKIE)
