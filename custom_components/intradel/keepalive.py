"""Keep the Intradel session cookie alive.

The login form is gated behind a server-verified invisible reCAPTCHA, so a
programmatic login/password POST is always rejected ("La verification anti-spam
a echoue") and a session cookie captured from a real browser is the only usable
credential. That cookie carries no Expires/Max-Age: it lives exactly as long as
PHP keeps its session file, which is refreshed by every request and garbage
collected after a period of inactivity.

The default poll interval (12 hours) is far longer than a usual PHP session
lifetime, so the session dies between two polls and the user has to capture a
fresh cookie. Touching the site more often than that timeout keeps the session
alive indefinitely, which is what this module does: a HEAD request on the data
page returns no body at all, refreshes the session, and doubles as a liveness
check (200 when the session is valid, a 302 to the login page when it is not).
"""

from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp

_LOGGER = logging.getLogger(__name__)

DATA_URL = "https://www.intradel.be/particulier/data.php"

# Comfortably below PHP's 24-minute default session.gc_maxlifetime. The site
# does not advertise its own value, so this errs on the safe side; a ping costs
# no payload at all.
DEFAULT_KEEPALIVE_INTERVAL = timedelta(minutes=15)


async def ping_session(session: aiohttp.ClientSession, cookie: str) -> bool:
    """Refresh the server-side session and report whether it is still valid.

    Redirects are not followed on purpose: the redirect itself is the signal.
    A network error is reported as "still valid" so a transient outage does not
    trigger a spurious re-authentication; a genuinely dead session is caught by
    the next real poll anyway.
    """
    try:
        async with session.head(
            DATA_URL, headers={"Cookie": cookie}, allow_redirects=False
        ) as resp:
            if resp.status == 200:
                return True
            _LOGGER.debug("Intradel session ping returned %s: session expired", resp.status)
            return False
    except aiohttp.ClientError as err:
        _LOGGER.debug("Intradel session ping failed (%s); assuming still valid", err)
        return True
