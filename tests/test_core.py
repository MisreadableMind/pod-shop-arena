"""Properties the rest of the system is built on.

If any of these break, the anchor stops meaning anything — so they are worth
testing directly rather than only through the pipeline.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from core.canonical import NotCanonical, canonical, canonical_decimal, leaf_hash
from core.merkle import EmptyTree, MerkleTree, verify_proof
from core.money import CurrencyMismatch, Money
from core.tiers import NoEvidence, Tier, min_tier


class TestCanonical:
    def test_equal_decimals_serialize_identically(self):
        # Decimal("1.1") and Decimal("1.10") are the same number. If they
        # hashed differently, two machines could disagree about a metric they
        # both computed correctly.
        assert canonical_decimal(Decimal("1.1")) == canonical_decimal(Decimal("1.10"))
        assert canonical(Decimal("2.50")) == canonical(Decimal("2.5"))

    def test_negative_zero_is_zero(self):
        assert canonical_decimal(Decimal("-0.0")) == canonical_decimal(Decimal("0"))

    def test_key_order_does_not_matter(self):
        assert canonical({"b": 1, "a": 2}) == canonical({"a": 2, "b": 1})

    def test_float_is_refused(self):
        with pytest.raises(NotCanonical):
            canonical({"nav": 41207338.22})

    def test_naive_datetime_is_refused(self):
        # There is no correct guess for what timezone a naive datetime meant.
        with pytest.raises(NotCanonical):
            canonical(datetime(2026, 1, 1))

    def test_aware_datetimes_normalize_to_utc(self):
        from datetime import timedelta

        utc = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        offset = datetime(
            2026, 1, 1, 14, 0, tzinfo=timezone(timedelta(hours=2))
        )
        assert canonical(utc) == canonical(offset)

    def test_leaf_kinds_are_domain_separated(self):
        payload = {"same": "bytes"}
        assert leaf_hash("document", payload) != leaf_hash("fact", payload)


class TestMerkle:
    def test_every_proof_verifies(self):
        leaves = [leaf_hash("fact", {"i": i}) for i in range(9)]
        tree = MerkleTree(leaves)
        for leaf in leaves:
            assert verify_proof(tree.proof_for(leaf), tree.root)

    def test_proof_fails_against_a_different_root(self):
        tree = MerkleTree([leaf_hash("fact", {"i": i}) for i in range(4)])
        assert not verify_proof(tree.proof_for(tree.leaves[0]), b"\x00" * 32)

    def test_root_is_order_independent(self):
        leaves = [leaf_hash("fact", {"i": i}) for i in range(6)]
        assert MerkleTree(leaves).root == MerkleTree(list(reversed(leaves))).root

    def test_changing_one_leaf_changes_the_root(self):
        base = [leaf_hash("fact", {"i": i}) for i in range(5)]
        altered = base[:-1] + [leaf_hash("fact", {"i": 999})]
        assert MerkleTree(base).root != MerkleTree(altered).root

    def test_empty_tree_is_refused(self):
        # An empty root is a commitment to nothing that still looks like one.
        with pytest.raises(EmptyTree):
            MerkleTree([])

    def test_odd_leaf_is_promoted_not_duplicated(self):
        # Duplicating the last leaf is the classic construction and the classic
        # bug: it lets two different leaf sets fold to the same root.
        three = [leaf_hash("fact", {"i": i}) for i in range(3)]
        four = three + [three[-1]]
        assert MerkleTree(three).root != MerkleTree(four).root


class TestMoney:
    def test_minor_units_are_exact(self):
        assert Money.from_decimal(Decimal("41207338.22"), "USD").minor == 4120733822

    def test_float_is_refused(self):
        with pytest.raises(TypeError):
            Money.from_decimal(1.5, "USD")  # type: ignore[arg-type]

    def test_sub_minor_precision_is_refused_rather_than_rounded(self):
        with pytest.raises(ValueError):
            Money.from_decimal(Decimal("1.005"), "USD")

    def test_currency_mismatch_raises(self):
        with pytest.raises(CurrencyMismatch):
            Money(100, "USD") + Money(100, "EUR")

    def test_zero_decimal_currency(self):
        assert Money.from_decimal(Decimal("1200"), "JPY").minor == 1200


class TestTiers:
    def test_ordering_runs_weakest_to_strongest(self):
        assert Tier.SELF_REPORTED < Tier.AGGREGATOR_ATTESTED < Tier.SOURCE_SIGNED

    def test_one_weak_input_caps_the_whole_metric(self):
        eleven_signed = [Tier.SOURCE_SIGNED] * 11
        assert min_tier(eleven_signed + [Tier.SELF_REPORTED]) is Tier.SELF_REPORTED

    def test_empty_input_is_fatal(self):
        # Returning SOURCE_SIGNED would invent trust; returning SELF_REPORTED
        # would hide that a metric was computed from nothing.
        with pytest.raises(NoEvidence):
            min_tier([])


class TestTierAssignment:
    def test_unverified_mail_falls_all_the_way_to_self_reported(self):
        from core.types import Channel, tier_for

        # Not aggregator_attested — nobody attested to anything.
        assert tier_for(Channel.EML_UPLOAD, False) is Tier.SELF_REPORTED
        assert tier_for(Channel.EML_UPLOAD, True) is Tier.SOURCE_SIGNED

    def test_csv_can_never_be_signed(self):
        from core.types import Channel, tier_for

        assert tier_for(Channel.CSV_UPLOAD, True) is Tier.SELF_REPORTED
