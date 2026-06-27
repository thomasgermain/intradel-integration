"""Shared constants and fixtures data for the Intradel tests."""

from typing import Any

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.intradel.const import CONF_TOWN

# Credentials/town used to build a config entry. AMAY is a real key of TOWNS_MAP.
USER_INPUT = {
    CONF_USERNAME: "user",
    CONF_PASSWORD: "secret",
    CONF_TOWN: "AMAY",
}

# Shape mirrors what pyintradel.api.get_data returns (list of bin/recypark dicts).
SAMPLE_DATA: list[dict[str, Any]] = [
    {
        "name": "ORGANIQUE",
        "start_date": "01-01-2026",
        "id": "123456",
        "details": [
            {"date": "20-01-2026", "detail": "34.0"},
            {"date": "17-02-2026", "detail": "27.0"},
        ],
        "total": "61",
    },
    {
        "name": "RECYPARC",
        "start_date": "01-01-2026",
        "id": "RECYPARC",
        "details": [
            {"date": "14-04-2026", "detail": "Encombrants (0.35 m³)"},
        ],
        "total": "1",
    },
]
