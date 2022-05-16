"""Interfaces with intrael sensors."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from . import IntradelCoordinator
from .const import ATTR_START_DATE, DOMAIN
from homeassistant.components.sensor import (
    SensorEntity,
)
from homeassistant.const import MASS_KILOGRAMS
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the intradel sensors."""
    sensors = []
    coord: IntradelCoordinator = hass.data[DOMAIN][entry.unique_id]["COORDINATOR"]

    if coord.data:
        for data in coord.data:
            sensors.append(IntradelSensor(coord, data))

    async_add_entities(sensors)
    return True


class IntradelSensor(CoordinatorEntity, SensorEntity):
    """Intradel sensor."""

    def __init__(self, coordinator: IntradelCoordinator, data) -> None:
        """Initialize entity."""

        super().__init__(coordinator)
        self._data = data
        _LOGGER.debug("Received data: " + str(data))

    @property
    def native_value(self) -> StateType:
        """Return the state of the entity."""
        return self._data.get("total")

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of this entity, if any."""
        return None if self.name == "RECYPARC" else MASS_KILOGRAMS

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._data.get("name")

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return entity specific state attributes."""
        return {
            ATTR_START_DATE: self._data.get("start_date"),
            "details": self._data.get("details"),
        }

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{DOMAIN}_{self._data.get('id')}"

    @property
    def device_info(self):
        """Return device specific attributes."""
        if self._data.get("name") != "RECYPARC":
            return {
                "identifiers": {(DOMAIN, self._data.get("id"))},
                "name": self.name,
                "manufacturer": DOMAIN,
                "model": "Bin",
            }
        return {}

    @property
    def icon(self) -> str | None:
        """Return the icon to use in the frontend, if any."""
        return "mdi:recycle" if self.name == "RECYPARC" else "mdi:trash-can"
