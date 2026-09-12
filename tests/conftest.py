"""Fixtures for the Intradel integration tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intradel.const import DOMAIN

from .const import COOKIE_INPUT, SAMPLE_DATA, USER_INPUT


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Enable loading of the custom integration in every test."""
    yield


@pytest.fixture(autouse=True)
def bypass_clientsession() -> Generator[None]:
    """Avoid building a real aiohttp connector in tests.

    A real connector spawns a daemon cleanup thread that pytest-homeassistant
    flags as a lingering thread. We never hit the network anyway (get_data is
    mocked), so a fake session is enough.
    """
    with (
        patch("custom_components.intradel.coordinator.async_create_clientsession"),
        patch("custom_components.intradel.config_flow.async_get_clientsession"),
    ):
        yield


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry for the integration."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Intradel",
        data=COOKIE_INPUT,
        options={},
    )


@pytest.fixture
def mock_legacy_config_entry() -> MockConfigEntry:
    """Return an entry created before the login/password method was removed.

    Such entries carry a username, password and town but no cookie, and can no
    longer authenticate: the site verifies an invisible reCAPTCHA server-side.
    """
    return MockConfigEntry(
        domain=DOMAIN,
        title="Intradel",
        data=USER_INPUT,
        options={},
    )


@pytest.fixture
def mock_get_data() -> Generator[AsyncMock]:
    """Patch the coordinator's call to pyintradel so no network access happens."""
    with patch(
        "custom_components.intradel.coordinator.get_data",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = SAMPLE_DATA
        yield mock
