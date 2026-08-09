"""The metrics engine. Pure, Decimal, and quantized on the way out.

Determinism is the whole job. Python's `decimal` is correctly rounded and
platform-independent, so with an explicit context and an explicit quantization
step the same facts produce the same digits on every machine — which is what
lets a Merkle root over these numbers mean anything.

Two judgement calls worth arguing about:

Drawdown is measured on the return index, not on NAV. A manager who returns
capital to investors has not lost money, and a drawdown series built from raw
NAV says he has. Building the index from linked periodic returns removes flows
from the picture, which is the only version an allocator should accept.

Gross is computed by adding observed fees back, and the fee model travels with
the number as an explicit input. Presenting a gross figure without saying what
was added back is how performance advertising goes wrong, and the SEC Marketing
Rule requires both figures side by side anyway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Context, Decimal, ROUND_HALF_EVEN
from typing import Any, Sequence

from core.metrics.series import Period, Series, periods_per_year
from core.tiers import Tier
from core.types import MetricResult

# 34 significant digits: far more than the inputs justify, so that rounding
# happens once, at the quantization step, instead of accumulating quietly.
CTX = Context(prec=34, rounding=ROUND_HALF_EVEN)

# Every metric value is pinned to this scale before it leaves the engine.
QUANT = Decimal("1E-10")

ONE = Decimal(1)
ZERO = Decimal(0)
DAYS_PER_YEAR = Decimal("365.25")


class Uncomputable(ValueError):
    """The series cannot support this calculation.

    Raised rather than returning a plausible-looking number. The pipeline turns
    it into a finding, because "we could not compute this and here is why" is a
    far better thing to show an allocator than a quietly wrong ratio.
    """


@dataclass(frozen=True, slots=True)
class FeeModel:
    """What gets added back to reach a gross figure.

    Observed fees are the commissions we extracted from signed documents. On a
    fund of any size they are rounding error — ninety dollars of commission
    against fifteen million of NAV does not move a return — so a gross figure
    that differs from net in any interesting way is almost always about
    management and performance fees, which no broker document reports.

    Those are therefore *modelled*, from terms the manager states, and the terms
    travel with every gross number as an explicit input. A gross figure without
    its fee terms attached is exactly the kind of performance advertising the
    Marketing Rule exists to stop.
    """

    basis: str = "observed"
    description: str = "Commissions and fees as extracted from source documents."
    management_bps_per_annum: Decimal = ZERO
    performance_bps_of_gain: Decimal = ZERO

    @property
    def models_anything(self) -> bool:
        return self.management_bps_per_annum > 0 or self.performance_bps_of_gain > 0

    def canonical_form(self) -> dict[str, Any]:
        return {
            "basis": self.basis,
            "description": self.description,
            "management_bps_per_annum": self.management_bps_per_annum,
            "performance_bps_of_gain": self.performance_bps_of_gain,
        }


TWO_AND_TWENTY = FeeModel(
    basis="observed_plus_stated_terms",
    description=(
        "Observed commissions, plus management and performance fees accrued from "
        "the terms the manager states. Not read from any signed document."
    ),
    management_bps_per_annum=Decimal(200),
    performance_bps_of_gain=Decimal(2000),
)


def modeled_fee_minor(period: Period, model: FeeModel) -> int:
    """Fees the manager charged that no broker statement itemizes.

    NAV is reported after fees, so reaching gross means adding them back:
    management accrues on the capital base pro rata, and performance is charged
    on the gain that remains once management has been taken.
    """
    if not model.models_anything:
        return 0

    base = Decimal(period.begin_minor)
    year_fraction = CTX.divide(Decimal(period.days), DAYS_PER_YEAR)
    management = CTX.multiply(
        CTX.multiply(base, CTX.divide(model.management_bps_per_annum, Decimal(10_000))),
        year_fraction,
    )

    gain_after_management = (
        Decimal(period.end_minor)
        + Decimal(period.fees_minor)
        + management
        - base
        - Decimal(period.net_flow_minor)
    )
    performance = ZERO
    if gain_after_management > 0:
        performance = CTX.multiply(
            gain_after_management,
            CTX.divide(model.performance_bps_of_gain, Decimal(10_000)),
        )

    return int((management + performance).to_integral_value(rounding=ROUND_HALF_EVEN))


@dataclass(frozen=True, slots=True)
class Config:
    risk_free_annual: Decimal = Decimal("0.04")
    var_confidence: Decimal = Decimal("0.95")
    fee_model: FeeModel = field(default_factory=FeeModel)

    def canonical_form(self) -> dict[str, Any]:
        return {
            "risk_free_annual": self.risk_free_annual,
            "var_confidence": self.var_confidence,
            "fee_model": self.fee_model.canonical_form(),
        }


# -- primitives -----------------------------------------------------------


def _q(value: Decimal) -> Decimal:
    quantized = CTX.quantize(value, QUANT)
    return abs(quantized) if quantized == 0 else quantized


def _pow(base: Decimal, exponent: Decimal) -> Decimal:
    """base ** exponent for real exponents, via ln/exp in a fixed context."""
    if base <= 0:
        raise Uncomputable("cannot raise a non-positive growth factor to a real power")
    return CTX.exp(CTX.multiply(exponent, CTX.ln(base)))


def _mean(values: Sequence[Decimal]) -> Decimal:
    return CTX.divide(sum(values, ZERO), Decimal(len(values)))


def _sample_stdev(values: Sequence[Decimal]) -> Decimal:
    if len(values) < 2:
        raise Uncomputable("standard deviation needs at least two observations")
    mean = _mean(values)
    total = sum((CTX.power(v - mean, 2) for v in values), ZERO)
    return CTX.sqrt(CTX.divide(total, Decimal(len(values) - 1)))


def period_return(period: Period, *, fee_model: FeeModel | None = None) -> Decimal:
    """Modified Dietz for one period.

    R = (EMV - BMV - F) / (BMV + Σ wᵢFᵢ), where each flow is weighted by the
    fraction of the period it was invested for. Day-weighting is what separates
    this from a naive return: two million arriving on the last day of the month
    did not have a month to work.

    `fee_model` of None gives the net return — the number as the investor
    experienced it. Passing a model adds fees back and gives gross.
    """
    begin = Decimal(period.begin_minor)
    end = Decimal(period.end_minor)
    if fee_model is not None:
        end += Decimal(period.fees_minor) + Decimal(modeled_fee_minor(period, fee_model))

    net_flow = Decimal(period.net_flow_minor)
    days = Decimal(period.days)

    weighted = ZERO
    for flow in period.flows:
        elapsed = Decimal((flow.on - period.start).days)
        if elapsed < 0:
            elapsed = ZERO
        if elapsed > days:
            elapsed = days
        weight = CTX.divide(days - elapsed, days)
        weighted += CTX.multiply(weight, Decimal(flow.amount_minor))

    denominator = begin + weighted
    if denominator <= 0:
        raise Uncomputable(
            f"period {period.start}..{period.end} has an average capital base of "
            f"{denominator} minor units; a return over it would be meaningless"
        )
    return CTX.divide(end - begin - net_flow, denominator)


def periodic_returns(series: Series, *, fee_model: FeeModel | None = None) -> list[Decimal]:
    return [period_return(p, fee_model=fee_model) for p in series.periods]


def return_index(returns: Sequence[Decimal]) -> list[Decimal]:
    """Cumulative growth of one unit, flows removed. Drawdown lives on this."""
    index = [ONE]
    for r in returns:
        index.append(CTX.multiply(index[-1], ONE + r))
    return index


def max_drawdown(returns: Sequence[Decimal]) -> Decimal:
    """Deepest peak-to-trough fall of the return index, as a negative ratio."""
    peak = ONE
    worst = ZERO
    for value in return_index(returns):
        if value > peak:
            peak = value
        if peak > 0:
            drop = CTX.divide(value - peak, peak)
            if drop < worst:
                worst = drop
    return worst


def historical_var(returns: Sequence[Decimal], confidence: Decimal) -> Decimal:
    """Nearest-rank historical VaR, returned as a positive loss ratio.

    No distribution is assumed. With twelve monthly observations a 95% VaR is
    simply the worst month, and saying so plainly beats fitting a normal to a
    dozen points and implying more precision than exists.
    """
    if not returns:
        raise Uncomputable("VaR needs at least one observation")
    alpha = ONE - confidence
    ordered = sorted(returns)
    rank = int(CTX.divide(CTX.multiply(alpha, Decimal(len(ordered))), ONE).to_integral_value(rounding="ROUND_CEILING"))
    index = max(rank - 1, 0)
    return -ordered[index]


# -- the engine -----------------------------------------------------------


def compute(series: Series, config: Config | None = None) -> tuple[MetricResult, ...]:
    """Every metric, net and gross, each carrying the weakest tier that fed it."""
    config = config or Config()
    if not series.periods:
        raise Uncomputable("no valuation periods in this series")

    ppy = periods_per_year(series.periods)
    total_days = Decimal(sum(p.days for p in series.periods))
    years = CTX.divide(total_days, DAYS_PER_YEAR)
    tier = series.tier

    results: list[MetricResult] = []
    for basis in ("net", "gross"):
        results.extend(
            _compute_basis(
                series,
                config,
                basis=basis,
                ppy=ppy,
                years=years,
                tier=tier,
            )
        )
    return tuple(results)


def _compute_basis(
    series: Series,
    config: Config,
    *,
    basis: str,
    ppy: Decimal,
    years: Decimal,
    tier: Tier,
) -> list[MetricResult]:
    fee_model = config.fee_model if basis == "gross" else None
    returns = periodic_returns(series, fee_model=fee_model)
    n = len(returns)

    shared: dict[str, Any] = {
        "periods": n,
        "period_start": series.start,
        "period_end": series.end,
        "periods_per_year": ppy,
        "years": _q(years),
        "currency": series.currency,
    }
    if fee_model is not None:
        shared["fee_model"] = fee_model.canonical_form()
        shared["observed_fees_minor"] = sum(p.fees_minor for p in series.periods)
        shared["modeled_fees_minor"] = sum(
            modeled_fee_minor(p, fee_model) for p in series.periods
        )

    def metric(
        key: str, value: Decimal, unit: str, formula: str, **inputs: Any
    ) -> MetricResult:
        return MetricResult(
            key=key,
            value=_q(value),
            unit=unit,
            formula=formula,
            tier=tier,
            basis=basis,
            inputs={**shared, **inputs},
        )

    results: list[MetricResult] = []

    growth = ONE
    for r in returns:
        growth = CTX.multiply(growth, ONE + r)
    cumulative = growth - ONE

    results.append(
        metric(
            "twr_cumulative",
            cumulative,
            "ratio",
            "Π(1 + Rᵢ) − 1, where Rᵢ is the Modified Dietz return of period i",
        )
    )

    # Whole-period Modified Dietz, kept alongside linked TWR because the two
    # disagree whenever flows are large, and the gap is informative.
    whole = _whole_period_dietz(series, fee_model=fee_model)
    results.append(
        metric(
            "modified_dietz",
            whole,
            "ratio",
            "(EMV − BMV − F) / (BMV + Σ wᵢFᵢ) across the whole series",
            net_flow_minor=sum(p.net_flow_minor for p in series.periods),
        )
    )

    if growth > 0 and years > 0:
        annualized = _pow(growth, CTX.divide(ONE, years)) - ONE
    else:
        annualized = Decimal(-1)
    results.append(
        metric(
            "twr_annualized",
            annualized,
            "ratio",
            "Π(1 + Rᵢ)^(1/years) − 1",
        )
    )

    drawdown = max_drawdown(returns)
    results.append(
        metric(
            "max_drawdown",
            drawdown,
            "ratio",
            "min over t of (Iₜ − peak(I)ₜ) / peak(I)ₜ, on the return index — "
            "flows removed, so a withdrawal is not counted as a loss",
        )
    )

    if n >= 2:
        stdev = _sample_stdev(returns)
        volatility = CTX.multiply(stdev, CTX.sqrt(ppy))
        results.append(
            metric(
                "volatility_annualized",
                volatility,
                "ratio",
                "sample stdev of periodic returns × √(periods per year)",
                periodic_stdev=_q(stdev),
            )
        )

        rf = config.risk_free_annual
        excess = annualized - rf
        if volatility > 0:
            results.append(
                metric(
                    "sharpe",
                    CTX.divide(excess, volatility),
                    "ratio",
                    "(annualized TWR − risk-free) / annualized volatility",
                    risk_free_annual=rf,
                )
            )

        downside = _downside_deviation(returns, rf, ppy)
        if downside > 0:
            results.append(
                metric(
                    "sortino",
                    CTX.divide(excess, downside),
                    "ratio",
                    "(annualized TWR − risk-free) / annualized downside deviation "
                    "below the risk-free rate",
                    risk_free_annual=rf,
                    downside_deviation=_q(downside),
                )
            )

    if drawdown < 0:
        results.append(
            metric(
                "calmar",
                CTX.divide(annualized, abs(drawdown)),
                "ratio",
                "annualized TWR / |max drawdown|",
            )
        )

    var = historical_var(returns, config.var_confidence)
    results.append(
        metric(
            "var_historical",
            var,
            "ratio",
            f"historical VaR at {config.var_confidence} confidence, nearest-rank, "
            "expressed as a positive loss over one period",
            confidence=config.var_confidence,
            method="nearest-rank, no distribution assumed",
        )
    )

    return results


def _whole_period_dietz(series: Series, *, fee_model: FeeModel | None) -> Decimal:
    first, last = series.periods[0], series.periods[-1]
    begin = Decimal(first.begin_minor)
    end = Decimal(last.end_minor)
    if fee_model is not None:
        end += Decimal(
            sum(p.fees_minor + modeled_fee_minor(p, fee_model) for p in series.periods)
        )

    total_days = Decimal(sum(p.days for p in series.periods))
    net_flow = ZERO
    weighted = ZERO
    elapsed_before = ZERO

    for period in series.periods:
        for flow in period.flows:
            offset = elapsed_before + Decimal((flow.on - period.start).days)
            weight = CTX.divide(total_days - offset, total_days)
            weighted += CTX.multiply(weight, Decimal(flow.amount_minor))
            net_flow += Decimal(flow.amount_minor)
        elapsed_before += Decimal(period.days)

    denominator = begin + weighted
    if denominator <= 0:
        raise Uncomputable(
            "whole-series average capital base is not positive; a return over it "
            "would be meaningless"
        )
    return CTX.divide(end - begin - net_flow, denominator)


def _downside_deviation(
    returns: Sequence[Decimal], risk_free_annual: Decimal, ppy: Decimal
) -> Decimal:
    """Deviation of the periods that fell short of the risk-free rate.

    Upside volatility is not risk, which is the entire reason Sortino exists
    next to Sharpe.
    """
    if len(returns) < 2:
        raise Uncomputable("downside deviation needs at least two observations")
    periodic_mar = _pow(ONE + risk_free_annual, CTX.divide(ONE, ppy)) - ONE
    shortfalls = [min(ZERO, r - periodic_mar) for r in returns]
    total = sum((CTX.power(s, 2) for s in shortfalls), ZERO)
    periodic = CTX.sqrt(CTX.divide(total, Decimal(len(returns) - 1)))
    return CTX.multiply(periodic, CTX.sqrt(ppy))
