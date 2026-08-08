"""Turning a bag of facts into an ordered series of valuation periods.

A period runs from one NAV observation to the next, and carries the flows that
landed inside it. That shape is what every metric downstream is computed from,
and building it is where most of the honesty lives: a withdrawal that gets
mistaken for a loss will quietly ruin a track record, and a NAV with no date
cannot be placed in the series at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable, Sequence

from core.tiers import Tier, min_tier
from core.types import Fact, FactKind


@dataclass(frozen=True, slots=True)
class Flow:
    """External money in or out. Positive is a contribution."""

    on: date
    amount_minor: int
    tier: Tier


@dataclass(frozen=True, slots=True)
class Period:
    start: date
    end: date
    begin_minor: int
    end_minor: int
    flows: tuple[Flow, ...]
    fees_minor: int
    tiers: tuple[Tier, ...]

    @property
    def days(self) -> int:
        return max((self.end - self.start).days, 1)

    @property
    def net_flow_minor(self) -> int:
        return sum(f.amount_minor for f in self.flows)

    @property
    def tier(self) -> Tier:
        return min_tier(self.tiers)


@dataclass(frozen=True, slots=True)
class Series:
    currency: str
    periods: tuple[Period, ...]
    observations: tuple[tuple[date, int], ...]

    def __bool__(self) -> bool:
        return bool(self.periods)

    @property
    def tier(self) -> Tier:
        return min_tier([t for p in self.periods for t in p.tiers])

    @property
    def start(self) -> date:
        return self.periods[0].start

    @property
    def end(self) -> date:
        return self.periods[-1].end


class InsufficientSeries(ValueError):
    """Fewer than two NAV observations. One point is a balance, not a record."""


def build_series(facts: Iterable[Fact], *, currency: str | None = None) -> Series:
    """Order NAV observations and slot flows and fees into the gaps between them.

    Facts in another currency are dropped rather than converted. Converting
    would mean inventing an FX rate nobody signed, which is precisely the kind
    of unsourced number this whole system exists to refuse.
    """
    facts = list(facts)
    navs = sorted(
        (f for f in facts if f.kind is FactKind.NAV and f.amount_minor is not None),
        key=lambda f: (f.as_of, f.amount_minor),
    )
    if currency is None:
        currency = navs[0].currency if navs else "USD"
    navs = [f for f in navs if f.currency == currency]

    # One NAV per date; a later duplicate replaces an earlier one.
    deduped: dict[date, Fact] = {}
    for fact in navs:
        deduped[fact.as_of] = fact
    ordered = [deduped[key] for key in sorted(deduped)]

    if len(ordered) < 2:
        raise InsufficientSeries(
            f"need at least two NAV observations in {currency} to compute a return, "
            f"found {len(ordered)}"
        )

    flows = sorted(
        (
            f
            for f in facts
            if f.kind is FactKind.CASH_FLOW
            and f.amount_minor is not None
            and f.currency == currency
        ),
        key=lambda f: f.as_of,
    )
    fees = [
        f
        for f in facts
        if f.kind is FactKind.FEE and f.amount_minor is not None and f.currency == currency
    ]

    periods: list[Period] = []
    for previous, current in zip(ordered, ordered[1:]):
        window_flows = tuple(
            Flow(on=f.as_of, amount_minor=f.amount_minor or 0, tier=f.tier)
            for f in flows
            if previous.as_of < f.as_of <= current.as_of
        )
        window_fees = [f for f in fees if previous.as_of < f.as_of <= current.as_of]

        tiers = (
            previous.tier,
            current.tier,
            *(f.tier for f in window_flows),
            *(f.tier for f in window_fees),
        )

        periods.append(
            Period(
                start=previous.as_of,
                end=current.as_of,
                begin_minor=previous.amount_minor or 0,
                end_minor=current.amount_minor or 0,
                flows=window_flows,
                # Fees arrive as negative amounts; the magnitude is what gets
                # added back to reach a gross figure.
                fees_minor=sum(abs(f.amount_minor or 0) for f in window_fees),
                tiers=tiers,
            )
        )

    return Series(
        currency=currency,
        periods=tuple(periods),
        observations=tuple((f.as_of, f.amount_minor or 0) for f in ordered),
    )


def periods_per_year(periods: Sequence[Period]) -> Decimal:
    """Infer the cadence from the data instead of assuming monthly.

    Snapped to a standard cadence so that a February one day short of a
    thirty-day month does not produce an annualization factor of 12.03 and a
    Sharpe ratio nobody can reproduce.
    """
    if not periods:
        return Decimal(12)
    total_days = sum(p.days for p in periods)
    average = Decimal(total_days) / Decimal(len(periods))
    standard = {
        Decimal(252): Decimal(1),  # daily, trading days
        Decimal(52): Decimal(7),
        Decimal(26): Decimal(14),
        Decimal(12): Decimal("30.4375"),
        Decimal(4): Decimal("91.3125"),
        Decimal(2): Decimal("182.625"),
        Decimal(1): Decimal("365.25"),
    }
    best, best_gap = Decimal(12), None
    for frequency, days in standard.items():
        gap = abs(average - days)
        if best_gap is None or gap < best_gap:
            best, best_gap = frequency, gap
    return best
