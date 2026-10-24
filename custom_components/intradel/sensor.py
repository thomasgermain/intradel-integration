"""Interfaces with intradel sensors."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfMass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_DETAILS, ATTR_START_DATE, DOMAIN, MANUFACTURER, RECYPARC_ID
from .coordinator import IntradelConfigEntry, IntradelCoordinator

_LOGGER = logging.getLogger(__name__)

# Entities are read-only and fed by the coordinator: no per-entity polling.
PARALLEL_UPDATES = 0

BIN_DESCRIPTION = SensorEntityDescription(
    key="bin",
    name=None,
    translation_key="bin",
    device_class=SensorDeviceClass.WEIGHT,
    native_unit_of_measurement=UnitOfMass.KILOGRAMS,
    state_class=SensorStateClass.TOTAL_INCREASING,
)
# A visit counter: no unit, no device class.
RECYPARC_DESCRIPTION = SensorEntityDescription(
    key="recyparc",
    name=None,
    translation_key="recyparc",
    state_class=SensorStateClass.TOTAL_INCREASING,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntradelConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the intradel sensors."""
    coordinator = entry.runtime_data
    known_ids: set[str] = set()

    @callback
    def _async_add_new_sensors() -> None:
        """Create a sensor for every item the site reports that has none yet.

        The first payload may be empty, and a bin (or the recypark) can show up
        later, so this runs on every coordinator update, not only at setup.
        """
        new_items = []
        for item in coordinator.data or []:
            if item["id"] not in known_ids:
                known_ids.add(item["id"])
                new_items.append(item)
        if new_items:
            async_add_entities(
                IntradelSensor(coordinator, item["id"], item["name"]) for item in new_items
            )

    _async_add_new_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_sensors))


class IntradelSensor(CoordinatorEntity[IntradelCoordinator], SensorEntity):
    """Intradel sensor."""

    _attr_attribution = "Data provided by Intradel"
    _attr_has_entity_name = True

    def __init__(self, coordinator: IntradelCoordinator, data_id: str, name: str) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self._data_id = data_id
        is_recyparc = data_id == RECYPARC_ID
        self.entity_description = RECYPARC_DESCRIPTION if is_recyparc else BIN_DESCRIPTION
        self._attr_unique_id = f"{DOMAIN}_{data_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, data_id)},
            name=name,
            manufacturer=MANUFACTURER,
            model="Recypark" if is_recyparc else "Bin",
        )

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
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return entity specific state attributes."""
        return {
            ATTR_START_DATE: self._data.get("start_date"),
            ATTR_DETAILS: self._data.get("details"),
        }
