"""Interfaces with intradel sensors."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_START_DATE, DOMAIN
from .coordinator import IntradelConfigEntry, IntradelCoordinator

_LOGGER = logging.getLogger(__name__)

# Entities are read-only and fed by the coordinator: no per-entity polling.
PARALLEL_UPDATES = 0

_RECYPARC = "RECYPARC"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntradelConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the intradel sensors."""
    coordinator = entry.runtime_data
    if coordinator.data:
        async_add_entities(IntradelSensor(coordinator, data["id"]) for data in coordinator.data)


class IntradelSensor(CoordinatorEntity[IntradelCoordinator], SensorEntity):
    """Intradel sensor."""

    _attr_attribution = "Data provided by Intradel"
    # Yearly cumulative value that resets at the start of each year.
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: IntradelCoordinator, data_id: str) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self._data_id = data_id
        self._attr_unique_id = f"{DOMAIN}_{data_id}"

    @property
    def _data(self) -> dict[str, Any]:
        """Resolve the current data for this sensor from the coordinator.

        Entities are long-lived, but each poll produces a fresh list of dicts,
        so we must look our entry up by id on every access instead of caching it.
        """
        for item in self.coordinator.data or []:
            if item.get("id") == self._data_id:
                return item
        return {}

    @property
    def available(self) -> bool:
        """Return True if the sensor's data is still present."""
        return super().available and bool(self._data)

    @property
    def native_value(self) -> StateType:
        """Return the state of the entity."""
        total = self._data.get("total")
        if total is None:
            return None
        try:
            return float(total)
        except (TypeError, ValueError):
            return None

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return the device class (weight for bins, none for recypark)."""
        return None if self.name == _RECYPARC else SensorDeviceClass.WEIGHT

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of this entity, if any."""
        return None if self.name == _RECYPARC else UnitOfMass.KILOGRAMS

    @property
    def name(self) -> str | None:
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
    def device_info(self) -> DeviceInfo:
        """Return device specific attributes."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._data_id)},
            name=self.name,
            manufacturer=DOMAIN,
            model="Recypark" if self.name == _RECYPARC else "Bin",
        )

    @property
    def icon(self) -> str | None:
        """Return the icon to use in the frontend, if any."""
        return "mdi:recycle" if self.name == _RECYPARC else "mdi:trash-can"
