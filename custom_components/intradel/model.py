"""Typed domain model for the data scraped by pyintradel.

pyintradel returns untyped ``list[dict[str, Any]]`` straight from the HTML
scraping, with every value as a string (dates as ``DD-MM-YYYY``, weights and
totals as decimal strings, recypark contents as free text). Business logic on
top of that is unmaintainable, so this module is the single place where the
scraped payload is validated and turned into typed objects.

Parsing is deliberately tolerant: a row the website renders in an unexpected way
is skipped with a warning rather than breaking the whole update, because the
upstream markup changes without notice.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

_LOGGER = logging.getLogger(__name__)

# The name the website uses for the recypark card; every other card is a bin.
RECYPARC = "RECYPARC"

# Known bin fractions, kept as plain strings: the website is the source of truth
# for these labels and an unknown one must not break parsing.
ORGANIC = "ORGANIQUE"
RESIDUAL = "RESIDUEL"

# Dates come as "20-01-2026"; the fallback covers the ISO form in case the
# website (or a future API) switches.
_DATE_FORMATS = ("%d-%m-%Y", "%Y-%m-%d")

# The "(0.35 m³)" quantity of one recypark item. Only the parenthesised part is
# matched: the label is whatever precedes it, so a label containing a comma
# ("Bois, non traite") survives instead of being cut at the comma.
_RECYPARC_QUANTITY = re.compile(r"\(\s*([\d.,]+)\s*([^)]*?)\s*\)")


def _parse_date(value: Any) -> date | None:
    """Parse a website date, returning None when it is unusable."""
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    _LOGGER.warning("Unparsable intradel date: %r", value)
    return None


def _parse_number(value: Any) -> float | None:
    """Parse a website number, tolerating a comma decimal separator."""
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    # Strip a trailing unit ("34.0 kg") and normalise the decimal separator.
    text = value.strip().replace(",", ".").split(" ")[0]
    try:
        return float(text)
    except ValueError:
        _LOGGER.warning("Unparsable intradel number: %r", value)
        return None


@dataclass(frozen=True, slots=True)
class Collection:
    """A single bin emptying: its date and the weight that was billed."""

    date: date
    weight: float


@dataclass(frozen=True, slots=True)
class RecyparcItem:
    """One line dropped off during a recypark visit."""

    label: str
    quantity: float
    unit: str


@dataclass(frozen=True, slots=True)
class RecyparcVisit:
    """A single recypark visit and everything dropped off during it."""

    date: date
    items: tuple[RecyparcItem, ...]
    # The unparsed website text, kept so nothing is silently lost.
    raw: str

    def volume(self, unit: str = "m³") -> float:
        """Total quantity of the items expressed in the given unit."""
        return sum(item.quantity for item in self.items if item.unit == unit)


@dataclass(frozen=True, slots=True)
class BinAccount:
    """A chipped bin (organic or residual) and its collections for a year."""

    name: str
    chip_id: str
    start_date: date
    collections: tuple[Collection, ...]
    # Total as reported by the website, used as a fallback and to cross-check
    # our own sum (the site may bill a rounded value).
    reported_total: float | None

    @property
    def total_weight(self) -> float:
        """Summed weight of the collections, falling back to the reported total."""
        if self.collections:
            return round(sum(item.weight for item in self.collections), 3)
        return self.reported_total or 0.0

    @property
    def collection_count(self) -> int:
        """Number of collections."""
        return len(self.collections)

    @property
    def last_collection(self) -> Collection | None:
        """Most recent collection, if any."""
        return max(self.collections, key=lambda item: item.date, default=None)


@dataclass(frozen=True, slots=True)
class RecyparcAccount:
    """The recypark visits for a year."""

    start_date: date
    visits: tuple[RecyparcVisit, ...]
    reported_total: float | None

    @property
    def visit_count(self) -> int:
        """Number of visits."""
        return len(self.visits)

    @property
    def total_volume(self) -> float:
        """Total volume dropped off, in cubic metres."""
        return round(sum(visit.volume() for visit in self.visits), 3)

    @property
    def last_visit(self) -> RecyparcVisit | None:
        """Most recent visit, if any."""
        return max(self.visits, key=lambda item: item.date, default=None)

    def volume_by_label(self) -> dict[str, float]:
        """Cubic metres dropped off, per item label."""
        totals: dict[str, float] = {}
        for visit in self.visits:
            for item in visit.items:
                if item.unit == "m³":
                    totals[item.label] = round(totals.get(item.label, 0.0) + item.quantity, 3)
        return totals


@dataclass(frozen=True, slots=True)
class Account:
    """Everything known about one household for one year."""

    year: int
    bins: tuple[BinAccount, ...]
    recyparc: RecyparcAccount | None

    def bin_by_name(self, name: str) -> BinAccount | None:
        """Return the bin with that name, if present."""
        for item in self.bins:
            if item.name == name:
                return item
        return None

    @property
    def total_weight(self) -> float:
        """Combined weight of every bin."""
        return round(float(sum(item.total_weight for item in self.bins)), 3)


def parse_recyparc_detail(detail: Any) -> tuple[RecyparcItem, ...]:
    """Parse a recypark detail string into typed items.

    ``"Encombrants (0.35 m³), Petits Bruns (0.00 pièce)"`` becomes two items.
    A string that matches nothing yields an empty tuple; the caller keeps the
    raw text either way.
    """
    if not isinstance(detail, str):
        return ()
    items: list[RecyparcItem] = []
    cursor = 0
    for match in _RECYPARC_QUANTITY.finditer(detail):
        # Everything since the previous item is this item's label; strip the
        # separator the website puts between items.
        label = detail[cursor : match.start()].strip().lstrip(",;").strip()
        cursor = match.end()
        value = _parse_number(match.group(1))
        if value is None or not label:
            continue
        items.append(RecyparcItem(label=label, quantity=value, unit=match.group(2).strip()))
    if not items and detail.strip():
        _LOGGER.debug("No recypark item recognised in %r", detail)
    return tuple(items)


def _parse_details(raw: Any) -> Iterable[tuple[date, str]]:
    """Yield the (date, detail) pairs of a card, skipping unusable rows."""
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return
    for row in raw:
        if not isinstance(row, Mapping):
            continue
        parsed = _parse_date(row.get("date"))
        if parsed is None:
            continue
        detail = row.get("detail")
        yield parsed, detail if isinstance(detail, str) else ""


def _parse_bin(card: Mapping[str, Any], start_date: date) -> BinAccount | None:
    """Build a BinAccount from a scraped card."""
    name = card.get("name")
    chip_id = card.get("id")
    if not isinstance(name, str) or not isinstance(chip_id, str):
        _LOGGER.warning("Skipping intradel card without a name or chip id: %r", card)
        return None

    collections: list[Collection] = []
    for when, detail in _parse_details(card.get("details")):
        weight = _parse_number(detail)
        if weight is None:
            continue
        collections.append(Collection(date=when, weight=weight))

    return BinAccount(
        name=name,
        chip_id=chip_id,
        start_date=start_date,
        collections=tuple(sorted(collections, key=lambda item: item.date)),
        reported_total=_parse_number(card.get("total")),
    )


def _parse_recyparc(card: Mapping[str, Any], start_date: date) -> RecyparcAccount:
    """Build a RecyparcAccount from a scraped card."""
    visits = [
        RecyparcVisit(date=when, items=parse_recyparc_detail(detail), raw=detail)
        for when, detail in _parse_details(card.get("details"))
    ]
    return RecyparcAccount(
        start_date=start_date,
        visits=tuple(sorted(visits, key=lambda item: item.date)),
        reported_total=_parse_number(card.get("total")),
    )


def parse_account(payload: Any, *, default_year: int | None = None) -> Account:
    """Turn a raw pyintradel payload into a typed Account.

    ``default_year`` is used when no card carries a usable start date; pass the
    current year so an empty or malformed payload still yields a usable object.
    """
    bins: list[BinAccount] = []
    recyparc: RecyparcAccount | None = None
    start_dates: list[date] = []

    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        _LOGGER.warning("Unexpected intradel payload type: %s", type(payload).__name__)
        payload = ()

    for card in payload:
        if not isinstance(card, Mapping):
            continue
        start_date = _parse_date(card.get("start_date"))
        if start_date is None:
            # The website always renders 01-01 of the current year; fall back to
            # it rather than dropping an otherwise valid card.
            year = default_year or date.today().year
            start_date = date(year, 1, 1)
        start_dates.append(start_date)

        if card.get("name") == RECYPARC:
            recyparc = _parse_recyparc(card, start_date)
        else:
            parsed = _parse_bin(card, start_date)
            if parsed is not None:
                bins.append(parsed)

    year = min(start_dates).year if start_dates else (default_year or date.today().year)
    return Account(year=year, bins=tuple(bins), recyparc=recyparc)
