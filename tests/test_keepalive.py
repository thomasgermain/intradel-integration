"""Test the session keep-alive."""

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.intradel.keepalive import DATA_URL, ping_session

COOKIE = "PHPSESSID=abc123"


def _session(status: int | None = None, error: Exception | None = None) -> MagicMock:
    """Build a fake aiohttp session whose HEAD returns a status (or raises)."""
    session = MagicMock()
    if error is not None:
        session.head = MagicMock(side_effect=error)
        return session

    response = MagicMock()
    response.status = status
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    session.head = MagicMock(return_value=context)
    return session


async def test_live_session() -> None:
    """A 200 means the session is still valid."""
    session = _session(status=200)

    assert await ping_session(session, COOKIE) is True
    session.head.assert_called_once_with(
        DATA_URL, headers={"Cookie": COOKIE}, allow_redirects=False
    )


async def test_expired_session() -> None:
    """The site redirects to the login page once the session is gone."""
    assert await ping_session(_session(status=302), COOKIE) is False


@pytest.mark.parametrize("status", [401, 403, 500])
async def test_any_non_200_is_treated_as_expired(status: int) -> None:
    """Anything but a 200 means the data page was not served."""
    assert await ping_session(_session(status=status), COOKIE) is False


async def test_network_error_does_not_invalidate_the_session() -> None:
    """A transient outage must not trigger a spurious re-authentication."""
    session = _session(error=aiohttp.ClientError("boom"))

    assert await ping_session(session, COOKIE) is True


async def test_redirects_are_not_followed() -> None:
    """Following the redirect would turn the expiry signal into a 200."""
    session = _session(status=200)
    await ping_session(session, COOKIE)

    assert session.head.call_args.kwargs["allow_redirects"] is False
