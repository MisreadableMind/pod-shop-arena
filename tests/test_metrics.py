"""The maths, checked against numbers worked out by hand.

An auditor's report on the calculation engine buys more trust than every proof
mechanism in the codebase put together, and this file is the part of that we can
write ourselves.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.metrics import (
    Config,
    FeeModel,
    InsufficientSeries,
    TWO_AND_TWENTY,
    build_series,
    compute,
    max_drawdown,
    period_return,
)
from core.tiers import Tier
from core.types import Fact, FactKind


def nav(day: date, minor: int, tier: Tier = Tier.SOURCE_SIGNED) -> Fact:
    return Fact(
        account_id="a",
        document_sha256=f"doc-{day}",
        as_of=day,
        kind=FactKind.NAV,
        tier=tier,
        currency="USD",
        amount_minor=minor,
    )


def flow(day: date, minor: int, tier: Tier = Tier.SOURCE_SIGNED) -> Fact:
    return Fact(
        account_id="a",
        document_sha256=f"flow-{day}",
        as_of=day,
        kind=FactKind.CASH_FLOW,
        tier=tier,
        currency="USD",
        amount_minor=minor,
    )


class TestModifiedDietz:
    def test_simple_growth(self):
        series = build_series([nav(date(2026, 1, 31), 100_000_000),
                               nav(date(2026, 2, 28), 110_000_000)])
        assert period_return(series.periods[0]) == Decimal("0.1")

    def test_flow_is_weighted_by_time_invested(self):
        """Two million arriving on the last day of the month did not have a
        month to work, and a naive return pretends it did."""
        series = build_series(
            [
                nav(date(2026, 1, 1), 100_000_000),
                nav(date(2026, 1, 31), 160_000_000),
                flow(date(2026, 1, 16), 50_000_000),  # day 15 of 30
            ]
        )
        # R = (160m - 100m - 50m) / (100m + (15/30)(50m)) = 10m / 125m = 0.08
        assert period_return(series.periods[0]) == Decimal("0.08")

    def test_a_flow_the_day_after_the_opening_nav_gets_nearly_full_weight(self):
        series = build_series(
            [
                nav(date(2026, 1, 1), 100_000_000),
                nav(date(2026, 1, 31), 210_000_000),
                flow(date(2026, 1, 2), 100_000_000),
            ]
        )
        # weight = (30 - 1) / 30
        expected = (Decimal(210_000_000) - 100_000_000 - 100_000_000) / (
            Decimal(100_000_000) + (Decimal(29) / 30) * 100_000_000
        )
        assert abs(period_return(series.periods[0]) - expected) < Decimal("1E-20")

    def test_a_flow_on_the_opening_nav_date_is_already_inside_that_nav(self):
        """NAV is struck at the end of the day, so money that arrived on the
        same date is already counted in the opening balance. Including it again
        would double-count the contribution and understate the return."""
        series = build_series(
            [
                nav(date(2026, 1, 1), 100_000_000),
                nav(date(2026, 1, 31), 110_000_000),
                flow(date(2026, 1, 1), 100_000_000),
            ]
        )
        assert series.periods[0].flows == ()
        assert period_return(series.periods[0]) == Decimal("0.1")


class TestDrawdown:
    def test_a_withdrawal_is_not_a_loss(self):
        """The judgement call worth arguing about. NAV fell 20%; the manager
        lost nothing. Drawdown is measured on the return index for exactly this
        reason."""
        facts = [
            nav(date(2026, 1, 31), 100_000_000),
            nav(date(2026, 2, 28), 80_000_000),
            nav(date(2026, 3, 31), 80_000_000),
            flow(date(2026, 2, 1), -20_000_000),
        ]
        series = build_series(facts)
        results = {(m.key, m.basis): m.value for m in compute(series)}
        assert results[("max_drawdown", "net")] == Decimal("0E-10")

    def test_a_real_loss_is_a_drawdown(self):
        facts = [
            nav(date(2026, 1, 31), 100_000_000),
            nav(date(2026, 2, 28), 80_000_000),
            nav(date(2026, 3, 31), 90_000_000),
        ]
        series = build_series(facts)
        results = {(m.key, m.basis): m.value for m in compute(series)}
        assert results[("max_drawdown", "net")] == Decimal("-0.2")

    def test_index_drawdown_directly(self):
        assert max_drawdown([Decimal("0.1"), Decimal("-0.5"), Decimal("0.2")]) == Decimal(
            "-0.5"
        )


class TestTierPropagation:
    def test_one_self_reported_nav_caps_every_metric(self):
        facts = [
            nav(date(2026, 1, 31), 100_000_000),
            nav(date(2026, 2, 28), 110_000_000),
            nav(date(2026, 3, 31), 120_000_000, tier=Tier.SELF_REPORTED),
        ]
        series = build_series(facts)
        assert series.tier is Tier.SELF_REPORTED
        assert all(m.tier is Tier.SELF_REPORTED for m in compute(series))


class TestNetAndGross:
    def test_gross_exceeds_net_once_fees_are_modelled(self):
        facts = [
            nav(date(2026, 1, 31), 1_000_000_000),
            nav(date(2026, 2, 28), 1_100_000_000),
            nav(date(2026, 3, 31), 1_200_000_000),
        ]
        series = build_series(facts)
        results = {(m.key, m.basis): m.value for m in compute(series, Config(fee_model=TWO_AND_TWENTY))}
        assert results[("twr_cumulative", "gross")] > results[("twr_cumulative", "net")]

    def test_with_no_fee_terms_gross_equals_net(self):
        """Commissions on a fund of any size are rounding error. Pretending
        otherwise would be theatre."""
        facts = [
            nav(date(2026, 1, 31), 1_000_000_000),
            nav(date(2026, 2, 28), 1_100_000_000),
            nav(date(2026, 3, 31), 1_200_000_000),
        ]
        series = build_series(facts)
        results = {(m.key, m.basis): m.value for m in compute(series, Config(fee_model=FeeModel()))}
        assert results[("twr_cumulative", "gross")] == results[("twr_cumulative", "net")]

    def test_the_fee_terms_travel_with_the_gross_number(self):
        facts = [nav(date(2026, 1, 31), 1_000_000_000), nav(date(2026, 2, 28), 1_100_000_000)]
        series = build_series(facts)
        gross = [m for m in compute(series, Config(fee_model=TWO_AND_TWENTY)) if m.basis == "gross"]
        assert all("fee_model" in m.inputs for m in gross)
        assert gross[0].inputs["fee_model"]["management_bps_per_annum"] == Decimal(200)


class TestRefusals:
    def test_one_observation_is_a_balance_not_a_record(self):
        with pytest.raises(InsufficientSeries):
            build_series([nav(date(2026, 1, 31), 100_000_000)])

    def test_mixed_currencies_are_not_silently_converted(self):
        """Converting would mean inventing an FX rate nobody signed."""
        euro = Fact(
            account_id="a",
            document_sha256="d",
            as_of=date(2026, 2, 28),
            kind=FactKind.NAV,
            tier=Tier.SOURCE_SIGNED,
            currency="EUR",
            amount_minor=110_000_000,
        )
        with pytest.raises(InsufficientSeries):
            build_series([nav(date(2026, 1, 31), 100_000_000), euro])


class TestCadence:
    def test_monthly_data_annualizes_by_twelve(self):
        facts = [nav(date(2026, m, 28), 100_000_000 + m) for m in range(1, 8)]
        series = build_series(facts)
        volatility = [m for m in compute(series) if m.key == "volatility_annualized"][0]
        assert volatility.inputs["periods_per_year"] == Decimal(12)
