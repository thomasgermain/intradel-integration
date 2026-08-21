"""Interfaces with intradel sensors."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfMass, UnitOfTime, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_START_DATE,
    CONF_MAX_COLLECTIONS,
    CURRENCY,
    DEFAULT_MAX_COLLECTIONS,
    DOMAIN,
)
from .coordinator import IntradelConfigEntry, IntradelCoordinator
from .model import Account, BinAccount
from .stats import (
    account_collection_quota,
    bin_stats,
    collection_quota,
)
from .tariff import CostBreakdown, FractionCost, compute_cost

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
    if not coordinator.data:
        return

    entities: list[SensorEntity] = [
        IntradelSensor(coordinator, data["id"]) for data in coordinator.data
    ]
    # Derived sensors: one set per chipped bin, plus the household-wide ones.
    for bin_account in coordinator.account.bins:
        entities.extend(
            IntradelBinSensor(coordinator, bin_account.name, bin_account.chip_id, description)
            for description in BIN_SENSORS
        )
    entities.extend(
        IntradelAccountSensor(coordinator, description) for description in ACCOUNT_SENSORS
    )
    async_add_entities(entities)


def _today() -> date:
    """Today in the user's timezone, so day counts match their calendar."""
    return dt_util.now().date()


@dataclass(frozen=True, kw_only=True)
class IntradelBinSensorDescription(SensorEntityDescription):
    """Describes a sensor derived from one bin's data."""

    # Kept as two callables rather than one taking everything: most sensors need
    # only the statistics or only the cost, and this keeps each lambda readable.
    value_fn: Callable[[BinAccount, FractionCost, int], StateType]


@dataclass(frozen=True, kw_only=True)
class IntradelAccountSensorDescription(SensorEntityDescription):
    """Describes a sensor derived from the whole household."""

    value_fn: Callable[[Account, CostBreakdown, int], StateType]


BIN_SENSORS: tuple[IntradelBinSensorDescription, ...] = (
    IntradelBinSensorDescription(
        key="cost",
        translation_key="cost",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY,
        value_fn=lambda _bin, cost, _max: cost.total,
    ),
    IntradelBinSensorDescription(
        key="quota_used",
        translation_key="quota_used",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:gauge",
        value_fn=lambda _bin, cost, _max: cost.quota_used,
    ),
    IntradelBinSensorDescription(
        key="quota_remaining",
        translation_key="quota_remaining",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        value_fn=lambda _bin, cost, _max: cost.remaining_kg,
    ),
    IntradelBinSensorDescription(
        key="collections",
        translation_key="collections",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:dump-truck",
        value_fn=lambda item, _cost, _max: item.collection_count,
    ),
    IntradelBinSensorDescription(
        key="collections_remaining",
        translation_key="collections_remaining",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:dump-truck",
        value_fn=lambda item, _cost, maximum: (
            collection_quota(item, _today(), max_collections=maximum).remaining
        ),
    ),
    IntradelBinSensorDescription(
        key="collections_used",
        translation_key="collections_used",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:gauge",
        value_fn=lambda item, _cost, maximum: (
            collection_quota(item, _today(), max_collections=maximum).used_pct
        ),
    ),
    IntradelBinSensorDescription(
        key="average_per_collection",
        translation_key="average_per_collection",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        value_fn=lambda item, _cost, _max: bin_stats(item, _today()).average_per_collection,
    ),
    IntradelBinSensorDescription(
        key="projected_weight",
        translation_key="projected_weight",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        icon="mdi:chart-line",
        value_fn=lambda item, _cost, _max: bin_stats(item, _today()).projected_year_end,
    ),
    IntradelBinSensorDescription(
        key="days_since_last_collection",
        translation_key="days_since_last_collection",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.DAYS,
        icon="mdi:calendar-clock",
        value_fn=lambda item, _cost, _max: bin_stats(item, _today()).days_since_last,
    ),
)


ACCOUNT_SENSORS: tuple[IntradelAccountSensorDescription, ...] = (
    IntradelAccountSensorDescription(
        key="total_cost",
        translation_key="total_cost",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY,
        value_fn=lambda _account, cost, _max: cost.total,
    ),
    IntradelAccountSensorDescription(
        key="total_weight",
        translation_key="total_weight",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        value_fn=lambda account, _cost, _max: account.total_weight,
    ),
    IntradelAccountSensorDescription(
        key="total_collections",
        translation_key="total_collections",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:dump-truck",
        value_fn=lambda account, _cost, maximum: (
            account_collection_quota(account, _today(), max_collections=maximum).collections
        ),
    ),
    IntradelAccountSensorDescription(
        key="total_collections_remaining",
        translation_key="total_collections_remaining",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:dump-truck",
        value_fn=lambda account, _cost, maximum: (
            account_collection_quota(account, _today(), max_collections=maximum).remaining
        ),
    ),
    IntradelAccountSensorDescription(
        key="recyparc_volume",
        translation_key="recyparc_volume",
        device_class=SensorDeviceClass.VOLUME,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:recycle",
        value_fn=lambda account, _cost, _max: (
            account.recyparc.total_volume if account.recyparc else None
        ),
    ),
)


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


class IntradelBinSensor(CoordinatorEntity[IntradelCoordinator], SensorEntity):
    """A figure derived from one bin: cost, quota, pace or projection."""

    _attr_attribution = "Data provided by Intradel"
    _attr_has_entity_name = True
    entity_description: IntradelBinSensorDescription

    def __init__(
        self,
        coordinator: IntradelCoordinator,
        name: str,
        chip_id: str,
        description: IntradelBinSensorDescription,
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._name = name
        self._chip_id = chip_id
        self._attr_unique_id = f"{DOMAIN}_{chip_id}_{description.key}"
        # Attach to the device the plain weight sensor already creates, so every
        # figure about one bin sits together.
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, chip_id)})

    @property
    def _bin(self) -> BinAccount | None:
        """Resolve this sensor's bin from the latest poll.

        Entities are long-lived while each poll rebuilds the account, so the
        lookup happens on every access rather than being cached.
        """
        return self.coordinator.account.bin_by_name(self._name)

    @property
    def available(self) -> bool:
        """Return True while the bin is still present in the data."""
        return super().available and self._bin is not None

    @property
    def native_value(self) -> StateType:
        """Return the state of the entity."""
        bin_account = self._bin
        if bin_account is None:
            return None
        cost = compute_cost(self.coordinator.account, self.coordinator.tariff)
        fraction = next(
            (item for item in cost.fractions if item.name == self._name),
            None,
        )
        if fraction is None:
            return None
        return self.entity_description.value_fn(bin_account, fraction, self._max_collections)

    @property
    def _max_collections(self) -> int:
        """Yearly allowance of emptyings, from the options."""
        return int(
            self.coordinator.config_entry.options.get(CONF_MAX_COLLECTIONS, DEFAULT_MAX_COLLECTIONS)
        )


class IntradelAccountSensor(CoordinatorEntity[IntradelCoordinator], SensorEntity):
    """A figure covering the whole household rather than a single bin."""

    _attr_attribution = "Data provided by Intradel"
    _attr_has_entity_name = True
    entity_description: IntradelAccountSensorDescription

    def __init__(
        self,
        coordinator: IntradelCoordinator,
        description: IntradelAccountSensorDescription,
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_account_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "account")},
            name="Intradel",
            manufacturer=DOMAIN,
            model="Household",
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the entity."""
        account = self.coordinator.account
        cost = compute_cost(account, self.coordinator.tariff)
        return self.entity_description.value_fn(account, cost, self._max_collections)

    @property
    def _max_collections(self) -> int:
        """Yearly allowance of emptyings, from the options."""
        return int(
            self.coordinator.config_entry.options.get(CONF_MAX_COLLECTIONS, DEFAULT_MAX_COLLECTIONS)
        )
