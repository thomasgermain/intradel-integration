"""Cost model for Intradel waste collection.

Intradel bills through the Walloon "cout-verite" scheme: each town sets its own
annual fee that includes a quota of kilograms and of emptyings, and charges per
unit beyond it. Rates differ per town and change every year, so nothing is
hardcoded here -- a Tariff is built from user configuration and this module only
applies it. Every quota can be expressed per inhabitant, which is how most towns
publish them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .model import ORGANIC, RESIDUAL, Account, BinAccount, RecyparcAccount


@dataclass(frozen=True, slots=True)
class FractionTariff:
    """What one bin fraction costs, beyond the annual fee's quota."""

    price_per_kg: float = 0.0
    price_per_collection: float = 0.0
    # Quotas covered by the annual fee. When per_inhabitant is True they are
    # multiplied by the household size.
    included_kg: float = 0.0
    included_collections: float = 0.0
    per_inhabitant: bool = False


@dataclass(frozen=True, slots=True)
class RecyparcTariff:
    """What recypark drop-offs cost, beyond the annual fee's quota."""

    price_per_m3: float = 0.0
    price_per_visit: float = 0.0
    included_m3: float = 0.0
    included_visits: float = 0.0
    per_inhabitant: bool = False


@dataclass(frozen=True, slots=True)
class Tariff:
    """A town's full pricing for one year."""

    annual_fee: float = 0.0
    household_size: int = 1
    # Keyed by the bin name the website uses ("ORGANIQUE", "RESIDUEL").
    fractions: Mapping[str, FractionTariff] = field(default_factory=dict)
    recyparc: RecyparcTariff | None = None
    currency: str = "EUR"

    def quota(self, base: float, per_inhabitant: bool) -> float:
        """Scale a quota by the household size when it is per-inhabitant."""
        return base * self.household_size if per_inhabitant else base


@dataclass(frozen=True, slots=True)
class FractionCost:
    """Cost breakdown for one bin fraction."""

    name: str
    weight: float
    included_kg: float
    billable_kg: float
    weight_cost: float
    collections: int
    included_collections: float
    billable_collections: float
    collection_cost: float

    @property
    def total(self) -> float:
        """Total cost for this fraction."""
        return round(self.weight_cost + self.collection_cost, 2)

    @property
    def remaining_kg(self) -> float:
        """Kilograms left in the quota (0 once exceeded)."""
        return round(max(0.0, self.included_kg - self.weight), 3)

    @property
    def quota_used(self) -> float | None:
        """Share of the kilogram quota consumed, as a percentage."""
        if self.included_kg <= 0:
            return None
        return round(self.weight / self.included_kg * 100, 1)


@dataclass(frozen=True, slots=True)
class RecyparcCost:
    """Cost breakdown for recypark usage."""

    volume: float
    included_m3: float
    billable_m3: float
    volume_cost: float
    visits: int
    included_visits: float
    billable_visits: float
    visit_cost: float

    @property
    def total(self) -> float:
        """Total recypark cost."""
        return round(self.volume_cost + self.visit_cost, 2)

    @property
    def remaining_m3(self) -> float:
        """Cubic metres left in the quota (0 once exceeded)."""
        return round(max(0.0, self.included_m3 - self.volume), 3)


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    """The full bill for one year."""

    year: int
    currency: str
    annual_fee: float
    fractions: tuple[FractionCost, ...]
    recyparc: RecyparcCost | None

    @property
    def variable_cost(self) -> float:
        """Everything billed on top of the annual fee."""
        extra = self.recyparc.total if self.recyparc else 0.0
        return round(sum(item.total for item in self.fractions) + extra, 2)

    @property
    def total(self) -> float:
        """Total bill, annual fee included."""
        return round(self.annual_fee + self.variable_cost, 2)


def _billable(used: float, included: float) -> float:
    """Units billed once the quota is consumed."""
    return round(max(0.0, used - included), 3)


def price_bin(bin_account: BinAccount, tariff: Tariff) -> FractionCost:
    """Price one bin fraction. An unconfigured fraction prices to zero."""
    rates = tariff.fractions.get(bin_account.name, FractionTariff())
    weight = bin_account.total_weight
    collections = bin_account.collection_count

    included_kg = tariff.quota(rates.included_kg, rates.per_inhabitant)
    included_collections = tariff.quota(rates.included_collections, rates.per_inhabitant)
    billable_kg = _billable(weight, included_kg)
    billable_collections = _billable(collections, included_collections)

    return FractionCost(
        name=bin_account.name,
        weight=weight,
        included_kg=included_kg,
        billable_kg=billable_kg,
        weight_cost=round(billable_kg * rates.price_per_kg, 2),
        collections=collections,
        included_collections=included_collections,
        billable_collections=billable_collections,
        collection_cost=round(billable_collections * rates.price_per_collection, 2),
    )


def price_recyparc(recyparc: RecyparcAccount, tariff: Tariff) -> RecyparcCost | None:
    """Price recypark usage, or None when no recypark tariff is configured."""
    rates = tariff.recyparc
    if rates is None:
        return None

    volume = recyparc.total_volume
    visits = recyparc.visit_count
    included_m3 = tariff.quota(rates.included_m3, rates.per_inhabitant)
    included_visits = tariff.quota(rates.included_visits, rates.per_inhabitant)
    billable_m3 = _billable(volume, included_m3)
    billable_visits = _billable(visits, included_visits)

    return RecyparcCost(
        volume=volume,
        included_m3=included_m3,
        billable_m3=billable_m3,
        volume_cost=round(billable_m3 * rates.price_per_m3, 2),
        visits=visits,
        included_visits=included_visits,
        billable_visits=billable_visits,
        visit_cost=round(billable_visits * rates.price_per_visit, 2),
    )


def compute_cost(account: Account, tariff: Tariff) -> CostBreakdown:
    """Price a whole year."""
    return CostBreakdown(
        year=account.year,
        currency=tariff.currency,
        annual_fee=round(tariff.annual_fee, 2),
        fractions=tuple(price_bin(item, tariff) for item in account.bins),
        recyparc=price_recyparc(account.recyparc, tariff) if account.recyparc else None,
    )


def build_tariff(
    *,
    household_size: int = 1,
    quota_organic_kg: float = 0.0,
    quota_residual_kg: float = 0.0,
    price_organic_per_kg: float = 0.0,
    price_residual_per_kg: float = 0.0,
    annual_fee: float = 0.0,
    recyparc: RecyparcTariff | None = None,
    currency: str = "EUR",
) -> Tariff:
    """Build a Tariff from flat values, the shape an options flow produces.

    The two kilogram quotas are per inhabitant, which is how towns publish them
    (e.g. 25 kg of organic and 50 kg of residual waste per person and per year),
    so they are scaled by the household size when the cost is computed.
    """
    return Tariff(
        annual_fee=annual_fee,
        household_size=household_size,
        fractions={
            ORGANIC: FractionTariff(
                price_per_kg=price_organic_per_kg,
                included_kg=quota_organic_kg,
                per_inhabitant=True,
            ),
            RESIDUAL: FractionTariff(
                price_per_kg=price_residual_per_kg,
                included_kg=quota_residual_kg,
                per_inhabitant=True,
            ),
        },
        recyparc=recyparc,
        currency=currency,
    )
