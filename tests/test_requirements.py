"""Test that the test environment matches the declared minimum Home Assistant."""

import json
from pathlib import Path

from homeassistant.const import __version__ as HA_VERSION


def test_tested_home_assistant_is_the_declared_minimum() -> None:
    """requirements_test.txt pins the test plugin that ships the hacs.json minimum."""
    hacs = json.loads((Path(__file__).parent.parent / "hacs.json").read_text())

    assert HA_VERSION == hacs["homeassistant"]
