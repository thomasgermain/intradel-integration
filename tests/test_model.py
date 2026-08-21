"""Test the typed domain model built on top of the scraped payload."""

from datetime import date

import pytest

from custom_components.intradel.model import (
    Account,
    BinAccount,
    Collection,
    parse_account,
    parse_recyparc_detail,
)

from .const import SAMPLE_DATA

# A payload with both bin fractions and two recypark visits, using the string
# quirks the website actually produces: comma decimals and a trailing unit.
RICH_DATA = [
    {
        "name": "ORGANIQUE",
        "start_date": "01-01-2026",
        "id": "123456",
        "details": [
            {"date": "20-01-2026", "detail": "34.0"},
            {"date": "17-02-2026", "detail": "27,0"},
        ],
        "total": "61",
    },
    {
        "name": "RESIDUEL",
        "start_date": "01-01-2026",
        "id": "78810",
        "details": [{"date": "07-04-2026", "detail": "11.5 kg"}],
        "total": "11.5",
    },
    {
        "name": "RECYPARC",
        "start_date": "01-01-2026",
        "id": "RECYPARC",
        "details": [
            {"date": "02-05-2026", "detail": "Encombrants (0.35 m³), Petits Bruns (1.00 pièce)"},
            {"date": "14-04-2026", "detail": "Inertes (2,00 m³)"},
        ],
        "total": "2",
    },
]


def test_parse_sample_payload() -> None:
    """The payload shipped by the website is parsed into typed accounts."""
    account = parse_account(SAMPLE_DATA)

    assert account.year == 2026
    assert len(account.bins) == 1
    assert account.recyparc is not None

    organic = account.bin_by_name("ORGANIQUE")
    assert organic is not None
    assert organic.chip_id == "123456"
    assert organic.collection_count == 2
    assert organic.total_weight == pytest.approx(61.0)
    assert organic.reported_total == pytest.approx(61.0)


def test_parse_number_quirks() -> None:
    """Comma decimals and trailing units are accepted."""
    account = parse_account(RICH_DATA)

    organic = account.bin_by_name("ORGANIQUE")
    residual = account.bin_by_name("RESIDUEL")
    assert organic is not None
    assert residual is not None
    assert organic.total_weight == pytest.approx(61.0)
    assert residual.total_weight == pytest.approx(11.5)
    assert account.total_weight == pytest.approx(72.5)


def test_collections_are_sorted_and_dated() -> None:
    """Collections are exposed in chronological order with parsed dates."""
    account = parse_account(RICH_DATA)
    recyparc = account.recyparc
    assert recyparc is not None

    # The website lists the visits newest-first in this payload.
    assert [visit.date for visit in recyparc.visits] == [date(2026, 4, 14), date(2026, 5, 2)]
    assert recyparc.last_visit is not None
    assert recyparc.last_visit.date == date(2026, 5, 2)


def test_recyparc_volume_ignores_non_volume_units() -> None:
    """Only cubic-metre items count towards the volume; pieces do not."""
    account = parse_account(RICH_DATA)
    recyparc = account.recyparc
    assert recyparc is not None

    assert recyparc.visit_count == 2
    assert recyparc.total_volume == pytest.approx(2.35)
    assert recyparc.volume_by_label() == {
        "Encombrants": pytest.approx(0.35),
        "Inertes": pytest.approx(2.0),
    }


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ("Encombrants (0.35 m³)", [("Encombrants", 0.35, "m³")]),
        # A label may itself contain a comma: it must not be cut at the comma.
        ("Bois, non traité (1.20 m³)", [("Bois, non traité", 1.2, "m³")]),
        (
            "Encombrants (0.35 m³), Inertes (2,00 m³)",
            [("Encombrants", 0.35, "m³"), ("Inertes", 2.0, "m³")],
        ),
        ("Petits Bruns (0.00 pièce)", [("Petits Bruns", 0.0, "pièce")]),
        ("Divers sans quantite", []),
        ("", []),
        (None, []),
    ],
)
def test_parse_recyparc_detail(detail: str | None, expected: list[tuple[str, float, str]]) -> None:
    """The free-text recypark detail is split into typed items."""
    items = parse_recyparc_detail(detail)
    assert [(item.label, item.quantity, item.unit) for item in items] == expected


def test_empty_payload_is_usable() -> None:
    """An empty payload yields an empty account rather than raising."""
    account = parse_account([], default_year=2030)

    assert account == Account(year=2030, bins=(), recyparc=None)
    assert account.total_weight == pytest.approx(0.0)
    assert account.bin_by_name("ORGANIQUE") is None


@pytest.mark.parametrize("payload", ["not a list", None, 42, {"name": "ORGANIQUE"}])
def test_malformed_payload_is_tolerated(payload: object) -> None:
    """A payload of the wrong shape falls back to the default year."""
    assert parse_account(payload, default_year=2030).year == 2030


def test_card_without_chip_id_is_skipped() -> None:
    """A bin card missing its identity is dropped, the rest is kept."""
    account = parse_account(
        [
            {"name": "ORGANIQUE", "start_date": "01-01-2026"},
            {
                "name": "RESIDUEL",
                "start_date": "01-01-2026",
                "id": "7",
                "details": [],
                "total": "3",
            },
        ]
    )

    assert [item.name for item in account.bins] == ["RESIDUEL"]


def test_unparsable_dates_are_skipped() -> None:
    """Rows with an unusable date are ignored; a bad start date falls back."""
    account = parse_account(
        [
            {
                "name": "ORGANIQUE",
                "start_date": "31-31-2026",
                "id": "1",
                "details": [
                    {"date": "", "detail": "10"},
                    {"date": "not a date", "detail": "10"},
                    {"date": "20-01-2026", "detail": "10"},
                ],
                "total": "10",
            }
        ],
        default_year=2026,
    )

    organic = account.bins[0]
    assert organic.collection_count == 1
    assert organic.start_date == date(2026, 1, 1)


def test_total_weight_falls_back_to_reported_total() -> None:
    """With no parsable collection, the website's own total is used."""
    account = parse_account(
        [{"name": "ORGANIQUE", "start_date": "01-01-2026", "id": "1", "details": [], "total": "99"}]
    )

    assert account.bins[0].total_weight == pytest.approx(99.0)


def test_last_collection() -> None:
    """The most recent collection is exposed, and None when there is none."""
    empty = BinAccount(
        name="ORGANIQUE",
        chip_id="1",
        start_date=date(2026, 1, 1),
        collections=(),
        reported_total=None,
    )
    assert empty.last_collection is None
    assert empty.total_weight == pytest.approx(0.0)

    filled = BinAccount(
        name="ORGANIQUE",
        chip_id="1",
        start_date=date(2026, 1, 1),
        collections=(
            Collection(date=date(2026, 1, 20), weight=10.0),
            Collection(date=date(2026, 3, 3), weight=20.0),
        ),
        reported_total=30.0,
    )
    assert filled.last_collection is not None
    assert filled.last_collection.date == date(2026, 3, 3)
