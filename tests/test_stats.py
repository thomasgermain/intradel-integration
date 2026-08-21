"""Test the trend and projection helpers."""

from datetime import date

import pytest

from custom_components.intradel.model import parse_account
from custom_components.intradel.stats import (
    ALL_BINS,
    DEFAULT_MAX_COLLECTIONS,
    Delta,
    YearSummary,
    account_collection_quota,
    bin_stats,
    collection_quota,
    compare_to_date,
    compare_years,
    elapsed_fraction,
    monthly_weight,
    project_year_end,
    summarize,
)

from .test_model import RICH_DATA

# 2 July 2026 is day 183 of a 365-day year: almost exactly half of it elapsed.
MIDYEAR = date(2026, 7, 2)

PREVIOUS = YearSummary(
    year=2025,
    total_weight=260.0,
    collection_count=11,
    recyparc_visits=5,
    recyparc_volume=4.0,
    weight_per_fraction={"ORGANIQUE": 200.0, "RESIDUEL": 60.0},
)


def test_elapsed_fraction() -> None:
    """The elapsed share is bounded, and complete for a year already over."""
    assert elapsed_fraction(2026, MIDYEAR) == pytest.approx(183 / 365)
    assert elapsed_fraction(2026, date(2026, 12, 31)) == pytest.approx(1.0)
    # 2024 is a leap year: 366 days.
    assert elapsed_fraction(2024, date(2024, 12, 31)) == pytest.approx(1.0)
    assert elapsed_fraction(2025, MIDYEAR) == pytest.approx(1.0)
    assert elapsed_fraction(2027, MIDYEAR) == pytest.approx(0.0)


def test_project_year_end() -> None:
    """A year-to-date value is extrapolated linearly on elapsed days."""
    assert project_year_end(100.0, 2026, MIDYEAR) == pytest.approx(199.45, abs=0.01)
    assert project_year_end(0.0, 2026, MIDYEAR) == pytest.approx(0.0)


def test_projection_is_suppressed_early_in_the_year() -> None:
    """Too few elapsed days would turn one emptying into an absurd yearly figure."""
    assert project_year_end(3.0, 2026, date(2026, 1, 1)) is None
    assert project_year_end(3.0, 2026, date(2026, 1, 20)) is None
    assert project_year_end(3.0, 2026, date(2026, 2, 15)) is not None
    # A year that has not started yet cannot be projected.
    assert project_year_end(10.0, 2027, MIDYEAR) is None


def test_monthly_weight() -> None:
    """Weights are grouped per calendar month."""
    account = parse_account(RICH_DATA)
    organic = account.bin_by_name("ORGANIQUE")
    assert organic is not None

    assert monthly_weight(organic) == {1: pytest.approx(34.0), 2: pytest.approx(27.0)}


def test_bin_stats() -> None:
    """Averages, extremes, recency and projection are derived from collections."""
    account = parse_account(RICH_DATA)
    organic = account.bin_by_name("ORGANIQUE")
    assert organic is not None

    stats = bin_stats(organic, MIDYEAR)
    assert stats.name == "ORGANIQUE"
    assert stats.collection_count == 2
    assert stats.average_per_collection == pytest.approx(30.5)
    assert stats.heaviest == pytest.approx(34.0)
    assert stats.last_collection == date(2026, 2, 17)
    assert stats.days_since_last == 135
    assert stats.projected_year_end == pytest.approx(121.67, abs=0.01)


def test_bin_stats_without_collections() -> None:
    """A bin with no collection reports no average and no recency."""
    account = parse_account(
        [{"name": "ORGANIQUE", "start_date": "01-01-2026", "id": "1", "details": [], "total": "0"}]
    )

    stats = bin_stats(account.bins[0], MIDYEAR)
    assert stats.collection_count == 0
    assert stats.average_per_collection is None
    assert stats.heaviest is None
    assert stats.last_collection is None
    assert stats.days_since_last is None
    assert stats.monthly_weight == {}


def test_summarize() -> None:
    """An account reduces to a compact, storable snapshot."""
    summary = summarize(parse_account(RICH_DATA))

    assert summary.year == 2026
    assert summary.total_weight == pytest.approx(72.5)
    assert summary.collection_count == 3
    assert summary.recyparc_visits == 2
    assert summary.recyparc_volume == pytest.approx(2.35)
    assert summary.weight_per_fraction == {
        "ORGANIQUE": pytest.approx(61.0),
        "RESIDUEL": pytest.approx(11.5),
    }


def test_summarize_empty_account() -> None:
    """An empty account summarises to zeros, not to None."""
    summary = summarize(parse_account([], default_year=2026))

    assert summary.total_weight == pytest.approx(0.0)
    assert summary.collection_count == 0
    assert summary.recyparc_visits == 0
    assert summary.weight_per_fraction == {}


def test_delta_change() -> None:
    """A delta exposes both the absolute and the relative change."""
    delta = Delta("total_weight", 120.0, 100.0)
    assert delta.change == pytest.approx(20.0)
    assert delta.change_pct == pytest.approx(20.0)


def test_delta_without_baseline() -> None:
    """A zero baseline makes the relative change undefined, not infinite."""
    assert Delta("total_weight", 5.0, 0.0).change_pct is None


def test_compare_years() -> None:
    """Every headline metric plus one per fraction is compared."""
    comparison = compare_years(summarize(parse_account(RICH_DATA)), PREVIOUS)

    assert comparison.year == 2026
    assert comparison.previous_year == 2025
    total = comparison.by_metric("total_weight")
    assert total is not None
    assert total.change == pytest.approx(-187.5)
    assert comparison.by_metric("weight:ORGANIQUE") is not None
    assert comparison.by_metric("weight:PMC") is None


def test_compare_years_covers_fractions_of_either_year() -> None:
    """A fraction present in only one of the two years still gets a delta."""
    previous = YearSummary(
        year=2025,
        total_weight=12.0,
        collection_count=1,
        recyparc_visits=0,
        recyparc_volume=0.0,
        weight_per_fraction={"PMC": 12.0},
    )
    comparison = compare_years(summarize(parse_account(RICH_DATA)), previous)

    pmc = comparison.by_metric("weight:PMC")
    assert pmc is not None
    assert pmc.current == pytest.approx(0.0)
    assert pmc.change_pct == pytest.approx(-100.0)


def test_compare_to_date_scales_the_baseline() -> None:
    """A part-year is compared against the same share of the previous year."""
    current = summarize(parse_account(RICH_DATA))

    naive = compare_years(current, PREVIOUS).by_metric("total_weight")
    fair = compare_to_date(current, PREVIOUS, MIDYEAR).by_metric("total_weight")
    assert naive is not None
    assert fair is not None

    # Half a year against a whole year looks like a 72% drop; against the same
    # share of that year, the household is actually 44% below last year's pace.
    assert naive.change_pct == pytest.approx(-72.1, abs=0.1)
    assert fair.previous == pytest.approx(260.0 * 183 / 365, abs=0.01)
    assert fair.change_pct == pytest.approx(-44.4, abs=0.1)


def test_collection_quota_within_allowance() -> None:
    """Emptyings are counted against the yearly allowance."""
    account = parse_account(RICH_DATA)
    organic = account.bin_by_name("ORGANIQUE")
    assert organic is not None

    quota = collection_quota(organic, MIDYEAR, max_collections=30)
    assert quota.name == "ORGANIQUE"
    assert quota.collections == 2
    assert quota.max_collections == 30
    assert quota.remaining == 28
    assert quota.used_pct == pytest.approx(6.7)
    assert quota.exceeded is False


def test_collection_quota_default_allowance() -> None:
    """The allowance defaults to 30 emptyings."""
    account = parse_account(RICH_DATA)
    organic = account.bin_by_name("ORGANIQUE")
    assert organic is not None

    assert collection_quota(organic, MIDYEAR).max_collections == DEFAULT_MAX_COLLECTIONS


def test_collection_quota_exceeded() -> None:
    """Going past the allowance is reported and the remainder floors at zero."""
    account = parse_account(RICH_DATA)
    organic = account.bin_by_name("ORGANIQUE")
    assert organic is not None

    quota = collection_quota(organic, MIDYEAR, max_collections=1)
    assert quota.exceeded is True
    assert quota.remaining == 0
    assert quota.used_pct == pytest.approx(200.0)


def test_collection_quota_projection() -> None:
    """The pace is extrapolated and compared against the allowance."""
    account = parse_account(RICH_DATA)
    organic = account.bin_by_name("ORGANIQUE")
    assert organic is not None

    # 2 emptyings at mid-year extrapolate to ~4 over the year.
    quota = collection_quota(organic, MIDYEAR, max_collections=3)
    assert quota.projected_collections == pytest.approx(3.99, abs=0.01)
    assert quota.projected_exceeded is True
    assert quota.projected_used_pct == pytest.approx(133.0, abs=1.0)

    within = collection_quota(organic, MIDYEAR, max_collections=30)
    assert within.projected_exceeded is False


def test_collection_quota_without_allowance() -> None:
    """With no allowance configured, the ratios are undefined rather than zero."""
    account = parse_account(RICH_DATA)
    organic = account.bin_by_name("ORGANIQUE")
    assert organic is not None

    quota = collection_quota(organic, MIDYEAR, max_collections=0)
    assert quota.used_pct is None
    assert quota.projected_used_pct is None
    assert quota.projected_exceeded is None
    assert quota.exceeded is False


def test_collection_quota_projection_unknown_early() -> None:
    """Early in the year the pace is not extrapolated at all."""
    account = parse_account(RICH_DATA)
    organic = account.bin_by_name("ORGANIQUE")
    assert organic is not None

    quota = collection_quota(organic, date(2026, 1, 5), max_collections=30)
    assert quota.projected_collections is None
    assert quota.projected_exceeded is None


def test_account_collection_quota_sums_every_bin() -> None:
    """The household-wide reading counts the emptyings of all bins together."""
    account = parse_account(RICH_DATA)

    quota = account_collection_quota(account, MIDYEAR, max_collections=30)
    assert quota.name == ALL_BINS
    # 2 organic + 1 residual.
    assert quota.collections == 3
    assert quota.remaining == 27


def test_account_collection_quota_empty_account() -> None:
    """With no bin at all the allowance is untouched."""
    quota = account_collection_quota(parse_account([], default_year=2026), MIDYEAR)

    assert quota.collections == 0
    assert quota.remaining == DEFAULT_MAX_COLLECTIONS
    assert quota.exceeded is False
