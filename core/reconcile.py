"""Where two sources cover the same period, they must agree.

A mismatch writes a finding; it never throws. Allocators care more about the
discrepancies we surface than the ones we hide, and a pipeline that halts on
disagreement just teaches everyone to stop sending the second source.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable

from core.tiers import Tier
from core.types import Fact, FactKind, Finding, Severity


def reconcile(facts: Iterable[Fact]) -> tuple[Finding, ...]:
    facts = list(facts)
    findings: list[Finding] = []
    findings.extend(_conflicting_navs(facts))
    findings.extend(_series_gaps(facts))
    findings.extend(_unmeasured_flows(facts))
    findings.extend(_weak_evidence(facts))
    return tuple(findings)


def _unmeasured_flows(facts: list[Fact]) -> list[Finding]:
    """Money that moved after the last valuation.

    A flow on or before the opening NAV is already inside that balance, which is
    correct. A flow *after* the closing NAV is not measured by anything: the
    return series ends before it, so its effect is invisible. Silently dropping
    it would make the record look complete when it isn't.
    """
    nav_dates = [f.as_of for f in facts if f.kind is FactKind.NAV]
    if not nav_dates:
        return []
    last = max(nav_dates)

    stranded = [
        f
        for f in facts
        if f.kind is FactKind.CASH_FLOW and f.as_of > last and f.amount_minor
    ]
    if not stranded:
        return []

    total = sum(f.amount_minor or 0 for f in stranded)
    return [
        Finding(
            kind="unmeasured_flow",
            severity=Severity.WARNING,
            as_of=min(f.as_of for f in stranded),
            detail=(
                f"{len(stranded)} cash flow(s) totalling {total} minor units are dated "
                f"after the last NAV observation on {last}. No valuation covers them, so "
                "their effect on the return is not measured here."
            ),
        )
    ]


def _conflicting_navs(facts: list[Fact]) -> list[Finding]:
    """Two documents, one date, two different NAVs. Somebody is wrong."""
    by_date: dict[tuple[date, str], list[Fact]] = defaultdict(list)
    for fact in facts:
        if fact.kind is FactKind.NAV and fact.amount_minor is not None:
            by_date[(fact.as_of, fact.currency)].append(fact)

    findings: list[Finding] = []
    for (as_of, currency), group in sorted(by_date.items()):
        amounts = {f.amount_minor for f in group}
        if len(amounts) <= 1:
            continue
        documents = sorted({f.document_sha256[:12] for f in group})
        spread = max(amounts) - min(amounts)  # type: ignore[type-var]
        findings.append(
            Finding(
                kind="nav_conflict",
                severity=Severity.CRITICAL,
                as_of=as_of,
                detail=(
                    f"{len(amounts)} different NAV values for {as_of} in {currency}, "
                    f"spread {spread} minor units, across documents {', '.join(documents)}. "
                    "The later document was used; both remain in evidence."
                ),
            )
        )
    return findings


def _series_gaps(facts: list[Fact]) -> list[Finding]:
    """A missing month in an otherwise monthly series.

    Worth saying out loud. The gap may be innocent, but a track record with a
    hole in it is exactly what a bad month looks like after somebody tidies up,
    and the reader should decide which it is.
    """
    dates = sorted({f.as_of for f in facts if f.kind is FactKind.NAV})
    if len(dates) < 3:
        return []

    gaps = [(later - earlier).days for earlier, later in zip(dates, dates[1:])]
    typical = sorted(gaps)[len(gaps) // 2]
    if typical <= 0:
        return []

    findings: list[Finding] = []
    for earlier, later in zip(dates, dates[1:]):
        span = (later - earlier).days
        # Two typical periods with nothing in between is a missing observation,
        # not a long month.
        if span > typical * 1.8:
            missing = round(span / typical) - 1
            findings.append(
                Finding(
                    kind="series_gap",
                    severity=Severity.WARNING,
                    as_of=earlier + timedelta(days=typical),
                    detail=(
                        f"{span} days between NAV observations on {earlier} and {later}, "
                        f"against a typical {typical}. Roughly {missing} observation(s) "
                        "are missing from the series."
                    ),
                )
            )
    return findings


def _weak_evidence(facts: list[Fact]) -> list[Finding]:
    """Name the facts that drag the whole record's tier down.

    A metric carries min(tier) over its inputs, so a single self-reported row
    decides the grade of a twelve-month number. If that is going to happen, the
    reader should be told which row did it.
    """
    weakest = min((f.tier for f in facts), default=None)
    if weakest is None or weakest is Tier.SOURCE_SIGNED:
        return []

    culprits = [f for f in facts if f.tier is weakest]
    documents = sorted({f.document_sha256[:12] for f in culprits})
    dates = sorted({f.as_of for f in culprits})
    span = f"{dates[0]}" if len(dates) == 1 else f"{dates[0]}..{dates[-1]}"

    return [
        Finding(
            kind="weak_evidence",
            severity=Severity.WARNING,
            as_of=dates[0],
            detail=(
                f"{len(culprits)} fact(s) at tier {weakest.slug} covering {span}, from "
                f"document(s) {', '.join(documents)}. Every metric spanning them is "
                f"capped at {weakest.slug}, however strong the rest of the evidence is."
            ),
        )
    ]
