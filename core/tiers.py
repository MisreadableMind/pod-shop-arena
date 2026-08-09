"""The trust ladder.

A tier is a property of *evidence*, never of a connector or a customer, and it
is computed, never asserted. A fact inherits the tier of the document it came
from; a metric carries min(tier) over every fact that fed it. One CSV row in a
twelve-month TWR drags the whole number to self_reported. That is correct and it
is the point.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Iterable


class Tier(IntEnum):
    """Ordered weakest to strongest, so min() is the propagation rule."""

    SELF_REPORTED = 0
    PLATFORM_OBSERVED = 1
    AGGREGATOR_ATTESTED = 2
    SOURCE_SIGNED = 3

    @property
    def slug(self) -> str:
        return self.name.lower()

    @property
    def label(self) -> str:
        return _LABELS[self]

    @property
    def meaning(self) -> str:
        return _MEANINGS[self]

    @classmethod
    def from_slug(cls, slug: str) -> Tier:
        try:
            return cls[slug.upper()]
        except KeyError:
            raise ValueError(f"unknown tier: {slug!r}") from None


_LABELS: dict[Tier, str] = {
    Tier.SOURCE_SIGNED: "Source-signed",
    Tier.AGGREGATOR_ATTESTED: "Aggregator-attested",
    Tier.PLATFORM_OBSERVED: "Platform-observed",
    Tier.SELF_REPORTED: "Self-reported",
}

_MEANINGS: dict[Tier, str] = {
    Tier.SOURCE_SIGNED: "The institution's own key verifies these bytes.",
    Tier.AGGREGATOR_ATTESTED: "A named third party pulled it.",
    Tier.PLATFORM_OBSERVED: "We saw it. Our word only.",
    Tier.SELF_REPORTED: "Nobody vouches.",
}


class NoEvidence(ValueError):
    """A tier was requested over an empty set of inputs.

    Deliberately fatal. Returning SOURCE_SIGNED would invent trust; returning
    SELF_REPORTED would hide the fact that a metric was computed from nothing.
    Either way the caller has a bug and should hear about it.
    """


def min_tier(tiers: Iterable[Tier]) -> Tier:
    """The weakest link. This is the only way a metric ever gets a tier."""
    materialized = list(tiers)
    if not materialized:
        raise NoEvidence("cannot compute a tier over zero inputs")
    return min(materialized)
