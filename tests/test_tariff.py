"""Test the cost model."""

import pytest

from custom_components.intradel.model import parse_account
from custom_components.intradel.tariff import (
    FractionTariff,
    RecyparcTariff,
    Tariff,
    build_tariff,
    compute_cost,
    price_bin,
    price_recyparc,
)

from .test_model import RICH_DATA

# A household of three with per-inhabitant quotas, the usual "cout-verite" shape:
# 20 kg/inhabitant of organic waste and 15 kg/inhabitant of residual waste are
# covered by the annual fee, plus one emptying per inhabitant.
TARIFF = Tariff(
    annual_fee=60.0,
    household_size=3,
    fractions={
        "ORGANIQUE": FractionTariff(price_per_kg=0.10, included_kg=20, per_inhabitant=True),
        "RESIDUEL": FractionTariff(
            price_per_kg=0.22,
            price_per_collection=0.60,
            included_kg=15,
            included_collections=1,
            per_inhabitant=True,
        ),
    },
    recyparc=RecyparcTariff(
        price_per_m3=15.0, included_m3=0.5, price_per_visit=5.0, included_visits=2
    ),
)


def test_quota_scales_with_household_size() -> None:
    """A per-inhabitant quota is multiplied by the household size."""
    assert TARIFF.quota(20, per_inhabitant=True) == pytest.approx(60.0)
    assert TARIFF.quota(20, per_inhabitant=False) == pytest.approx(20.0)


def test_weight_beyond_the_quota_is_billed() -> None:
    """Only the kilograms past the quota are charged."""
    account = parse_account(RICH_DATA)
    organic = account.bin_by_name("ORGANIQUE")
    assert organic is not None

    cost = price_bin(organic, TARIFF)
    # 61 kg used, 3 x 20 kg included -> 1 kg billed at 0.10.
    assert cost.included_kg == pytest.approx(60.0)
    assert cost.billable_kg == pytest.approx(1.0)
    assert cost.weight_cost == pytest.approx(0.10)
    assert cost.total == pytest.approx(0.10)


def test_usage_within_the_quota_is_free() -> None:
    """Staying inside the quota costs nothing and leaves a remainder."""
    account = parse_account(RICH_DATA)
    residual = account.bin_by_name("RESIDUEL")
    assert residual is not None

    cost = price_bin(residual, TARIFF)
    # 11.5 kg used of 45 kg included, 1 emptying of 3 included.
    assert cost.billable_kg == pytest.approx(0.0)
    assert cost.billable_collections == pytest.approx(0.0)
    assert cost.total == pytest.approx(0.0)
    assert cost.remaining_kg == pytest.approx(33.5)
    assert cost.quota_used == pytest.approx(25.6)


def test_collections_beyond_the_quota_are_billed() -> None:
    """Emptyings are charged separately from weight once their quota is used."""
    account = parse_account(RICH_DATA)
    organic = account.bin_by_name("ORGANIQUE")
    assert organic is not None

    tariff = Tariff(
        household_size=1,
        fractions={"ORGANIQUE": FractionTariff(price_per_collection=1.50, included_collections=1)},
    )
    cost = price_bin(organic, tariff)
    # 2 emptyings, 1 included -> 1 billed at 1.50.
    assert cost.billable_collections == pytest.approx(1.0)
    assert cost.collection_cost == pytest.approx(1.50)
    assert cost.weight_cost == pytest.approx(0.0)


def test_quota_used_without_a_quota() -> None:
    """With no kilogram quota configured, the percentage is undefined."""
    account = parse_account(RICH_DATA)
    organic = account.bin_by_name("ORGANIQUE")
    assert organic is not None

    assert price_bin(organic, Tariff()).quota_used is None


def test_recyparc_volume_and_visits() -> None:
    """Recypark volume past the quota is billed; visits within it are not."""
    account = parse_account(RICH_DATA)
    assert account.recyparc is not None

    cost = price_recyparc(account.recyparc, TARIFF)
    assert cost is not None
    # 2.35 m3 used, 0.5 included -> 1.85 m3 at 15.00; 2 visits, 2 included.
    assert cost.billable_m3 == pytest.approx(1.85)
    assert cost.volume_cost == pytest.approx(27.75)
    assert cost.billable_visits == pytest.approx(0.0)
    assert cost.total == pytest.approx(27.75)
    assert cost.remaining_m3 == pytest.approx(0.0)


def test_no_recyparc_tariff_configured() -> None:
    """Without a recypark tariff, no recypark cost is produced."""
    account = parse_account(RICH_DATA)
    assert account.recyparc is not None

    assert price_recyparc(account.recyparc, Tariff()) is None


def test_full_breakdown_adds_up() -> None:
    """The total is the annual fee plus every variable component."""
    breakdown = compute_cost(parse_account(RICH_DATA), TARIFF)

    assert breakdown.year == 2026
    assert breakdown.currency == "EUR"
    assert breakdown.annual_fee == pytest.approx(60.0)
    assert {item.name for item in breakdown.fractions} == {"ORGANIQUE", "RESIDUEL"}
    assert breakdown.variable_cost == pytest.approx(27.85)
    assert breakdown.total == pytest.approx(87.85)


def test_unconfigured_tariff_prices_to_zero() -> None:
    """An empty tariff is valid: everything is free, nothing raises."""
    breakdown = compute_cost(parse_account(RICH_DATA), Tariff())

    assert breakdown.total == pytest.approx(0.0)
    assert breakdown.recyparc is None
    assert all(item.total == pytest.approx(0.0) for item in breakdown.fractions)


def test_empty_account_prices_to_the_annual_fee() -> None:
    """With no data at all, only the fixed fee is due."""
    breakdown = compute_cost(parse_account([], default_year=2026), TARIFF)

    assert breakdown.fractions == ()
    assert breakdown.recyparc is None
    assert breakdown.total == pytest.approx(60.0)


def test_build_tariff_from_flat_options() -> None:
    """The options-flow shape produces per-inhabitant kilogram quotas."""
    tariff = build_tariff(
        household_size=4,
        quota_organic_kg=25.0,
        quota_residual_kg=50.0,
        price_organic_per_kg=0.10,
        price_residual_per_kg=0.20,
        annual_fee=75.0,
    )

    assert tariff.household_size == 4
    assert tariff.fractions["ORGANIQUE"].included_kg == pytest.approx(25.0)
    assert tariff.fractions["ORGANIQUE"].per_inhabitant is True
    assert tariff.quota(tariff.fractions["RESIDUEL"].included_kg, per_inhabitant=True) == (
        pytest.approx(200.0)
    )
    assert tariff.recyparc is None


def test_build_tariff_scales_quotas_by_household() -> None:
    """A four-person household gets four times the per-person quota."""
    account = parse_account(RICH_DATA)
    organic = account.bin_by_name("ORGANIQUE")
    assert organic is not None

    solo = price_bin(
        organic, build_tariff(household_size=1, quota_organic_kg=25.0, price_organic_per_kg=0.10)
    )
    family = price_bin(
        organic, build_tariff(household_size=4, quota_organic_kg=25.0, price_organic_per_kg=0.10)
    )

    # 61 kg against 25 kg alone -> 36 kg billed; against 100 kg -> nothing.
    assert solo.billable_kg == pytest.approx(36.0)
    assert solo.weight_cost == pytest.approx(3.60)
    assert family.billable_kg == pytest.approx(0.0)
    assert family.remaining_kg == pytest.approx(39.0)
