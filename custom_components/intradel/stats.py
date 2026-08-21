"""Trends and projections derived from the scraped Intradel data.

Pure functions over the typed model: the caller passes "today" instead of
reading the clock, so results are deterministic and testable, and Home Assistant
can pass its own timezone-aware date.

Year-over-year comparison works on YearSummary objects rather than on Accounts,
because the website only exposes the current year: previous years have to come
from a stored summary (see compare_years).
"""

from __future__ import annotations

import calendar
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from .model import Account, BinAccount, RecyparcAccount

# Below this share of the year elapsed (~1 month), a linear projection is noise
# rather than a trend, so project_year_end reports nothing.
_MIN_ELAPSED = 30 / 365

# Yearly allowance of bin emptyings. Intradel bills emptyings on top of weight,
# so this is a quota in its own right; the value is town-specific and therefore
# configurable, 30 being the usual allowance.
DEFAULT_MAX_COLLECTIONS = 30

# Name used for the aggregate quota covering every bin at once.
ALL_BINS = "TOTAL"


def _days_in_year(year: int) -> int:
    """366 on a leap year, 365 otherwise."""
    return 366 if calendar.isleap(year) else 365


def _pct_change(current: float, previous: float) -> float | None:
    """Relative change in percent, or None when there is no baseline."""
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


@dataclass(frozen=True, slots=True)
class BinStats:
    """Derived figures for one bin fraction."""

    name: str
    total_weight: float
    collection_count: int
    average_per_collection: float | None
    heaviest: float | None
    last_collection: date | None
    days_since_last: int | None
    # Kilograms per calendar month, for the months that had a collection.
    monthly_weight: Mapping[int, float]
    projected_year_end: float | None


@dataclass(frozen=True, slots=True)
class YearSummary:
    """Compact, storable snapshot of one year -- the unit of comparison.

    Small and JSON-friendly on purpose: it is what an integration persists to
    still be able to compare years after the website has rolled over to 1 Jan.
    """

    year: int
    total_weight: float
    collection_count: int
    recyparc_visits: int
    recyparc_volume: float
    # Kilograms per bin name.
    weight_per_fraction: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Delta:
    """One metric compared against the same metric a year earlier."""

    metric: str
    current: float
    previous: float

    @property
    def change(self) -> float:
        """Absolute change."""
        return round(self.current - self.previous, 3)

    @property
    def change_pct(self) -> float | None:
        """Relative change in percent, None when the baseline is zero."""
        return _pct_change(self.current, self.previous)


@dataclass(frozen=True, slots=True)
class YearComparison:
    """A full year-over-year comparison."""

    year: int
    previous_year: int
    deltas: tuple[Delta, ...]

    def by_metric(self, metric: str) -> Delta | None:
        """Return the delta for that metric, if computed."""
        for item in self.deltas:
            if item.metric == metric:
                return item
        return None


def elapsed_fraction(year: int, today: date) -> float:
    """Share of `year` already elapsed on `today`, in the range 0-1.

    Returns 1.0 for a year already over and a small positive value on 1 Jan, so
    it is always safe to divide by.
    """
    if today.year > year:
        return 1.0
    if today.year < year:
        return 0.0
    day_of_year = today.timetuple().tm_yday
    return day_of_year / _days_in_year(year)


def project_year_end(
    value: float, year: int, today: date, *, min_elapsed: float = _MIN_ELAPSED
) -> float | None:
    """Extrapolate a year-to-date value to the end of the year.

    A plain linear extrapolation on elapsed days: it says "at this pace", which
    is what a quota warning needs. Returns None before the year has started, and
    while less than `min_elapsed` of it has passed: dividing by a handful of days
    turns a single emptying into an absurd yearly figure (3 kg on 1 January
    projects to over a tonne), which would fire false quota alerts every January.
    """
    elapsed = elapsed_fraction(year, today)
    if elapsed < min_elapsed or elapsed <= 0:
        return None
    return round(value / elapsed, 2)


def monthly_weight(bin_account: BinAccount) -> dict[int, float]:
    """Kilograms per calendar month, keyed by month number."""
    totals: dict[int, float] = {}
    for item in bin_account.collections:
        totals[item.date.month] = round(totals.get(item.date.month, 0.0) + item.weight, 3)
    return totals


def bin_stats(bin_account: BinAccount, today: date) -> BinStats:
    """Derive the trend figures of one bin fraction."""
    collections = bin_account.collections
    total = bin_account.total_weight
    last = bin_account.last_collection
    year = bin_account.start_date.year

    return BinStats(
        name=bin_account.name,
        total_weight=total,
        collection_count=len(collections),
        average_per_collection=round(total / len(collections), 2) if collections else None,
        heaviest=max((item.weight for item in collections), default=None),
        last_collection=last.date if last else None,
        days_since_last=(today - last.date).days if last else None,
        monthly_weight=monthly_weight(bin_account),
        projected_year_end=project_year_end(total, year, today),
    )


@dataclass(frozen=True, slots=True)
class CollectionQuota:
    """How many emptyings were used against the yearly allowance.

    Both the count and the allowance are plain numbers, so the same object
    describes a single bin or every bin at once.
    """

    name: str
    collections: int
    max_collections: int
    # Emptyings expected by 31 December at the current pace, None too early in
    # the year for the extrapolation to mean anything.
    projected_collections: float | None

    @property
    def remaining(self) -> int:
        """Emptyings left in the allowance (0 once it is used up)."""
        return max(0, self.max_collections - self.collections)

    @property
    def used_pct(self) -> float | None:
        """Share of the allowance used, None when no allowance is set."""
        if self.max_collections <= 0:
            return None
        return round(self.collections / self.max_collections * 100, 1)

    @property
    def exceeded(self) -> bool:
        """True once the allowance is used up."""
        return self.max_collections > 0 and self.collections > self.max_collections

    @property
    def projected_used_pct(self) -> float | None:
        """Share of the allowance the current pace leads to by year end."""
        if self.max_collections <= 0 or self.projected_collections is None:
            return None
        return round(self.projected_collections / self.max_collections * 100, 1)

    @property
    def projected_exceeded(self) -> bool | None:
        """Whether the current pace overshoots the allowance, None if unknown."""
        if self.max_collections <= 0 or self.projected_collections is None:
            return None
        return self.projected_collections > self.max_collections


def collection_quota(
    bin_account: BinAccount,
    today: date,
    *,
    max_collections: int = DEFAULT_MAX_COLLECTIONS,
) -> CollectionQuota:
    """Emptyings used against the allowance, for one bin."""
    count = bin_account.collection_count
    return CollectionQuota(
        name=bin_account.name,
        collections=count,
        max_collections=max_collections,
        projected_collections=project_year_end(count, bin_account.start_date.year, today),
    )


def account_collection_quota(
    account: Account,
    today: date,
    *,
    max_collections: int = DEFAULT_MAX_COLLECTIONS,
) -> CollectionQuota:
    """Emptyings used against the allowance, summed over every bin.

    Towns express the allowance either per bin or for the household as a whole;
    this is the household-wide reading, `collection_quota` the per-bin one.
    """
    count = sum(item.collection_count for item in account.bins)
    return CollectionQuota(
        name=ALL_BINS,
        collections=count,
        max_collections=max_collections,
        projected_collections=project_year_end(count, account.year, today),
    )


def summarize(account: Account) -> YearSummary:
    """Reduce an Account to a storable snapshot."""
    recyparc: RecyparcAccount | None = account.recyparc
    return YearSummary(
        year=account.year,
        total_weight=account.total_weight,
        collection_count=sum(item.collection_count for item in account.bins),
        recyparc_visits=recyparc.visit_count if recyparc else 0,
        recyparc_volume=recyparc.total_volume if recyparc else 0.0,
        weight_per_fraction={item.name: item.total_weight for item in account.bins},
    )


def compare_years(current: YearSummary, previous: YearSummary) -> YearComparison:
    """Compare two year snapshots, metric by metric.

    Per-fraction metrics are emitted for every fraction seen in either year, so
    a bin that appeared or disappeared still shows up (against a zero baseline).
    """
    deltas = [
        Delta("total_weight", current.total_weight, previous.total_weight),
        Delta("collection_count", current.collection_count, previous.collection_count),
        Delta("recyparc_visits", current.recyparc_visits, previous.recyparc_visits),
        Delta("recyparc_volume", current.recyparc_volume, previous.recyparc_volume),
    ]
    for name in sorted({*current.weight_per_fraction, *previous.weight_per_fraction}):
        deltas.append(
            Delta(
                f"weight:{name}",
                current.weight_per_fraction.get(name, 0.0),
                previous.weight_per_fraction.get(name, 0.0),
            )
        )
    return YearComparison(year=current.year, previous_year=previous.year, deltas=tuple(deltas))


def compare_to_date(current: YearSummary, previous: YearSummary, today: date) -> YearComparison:
    """Compare a partial year against the same share of the previous year.

    Comparing a year-to-date total against a full previous year always looks
    like an improvement; this scales the baseline down to the elapsed share of
    the year so the comparison is fair.
    """
    share = elapsed_fraction(current.year, today)
    scaled = YearSummary(
        year=previous.year,
        total_weight=round(previous.total_weight * share, 3),
        collection_count=round(previous.collection_count * share),
        recyparc_visits=round(previous.recyparc_visits * share),
        recyparc_volume=round(previous.recyparc_volume * share, 3),
        weight_per_fraction={
            name: round(value * share, 3) for name, value in previous.weight_per_fraction.items()
        },
    )
    return compare_years(current, scaled)
