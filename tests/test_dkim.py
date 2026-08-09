"""The DKIM fixture corpus.

A corpus of real signed messages: valid, l=-tagged, key-rotated, body-tampered
by one byte, forwarded-and-broken. Each has an expected verdict, and the whole
point is that these run against actual RSA rather than a mock — a mocked
verifier would happily agree with whatever we told it.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.dkim import required_dns_names, signatures, verify_message

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def verdict_for(raw, corpus, institutions, records=None):
    return verify_message(
        raw,
        dns_records=records if records is not None else corpus.captured_dns,
        institutions=institutions,
        captured_at=NOW,
    )


def test_every_fixture_matches_its_expected_verdict(corpus, institutions):
    failures = []
    for fixture in corpus.fixtures:
        analysis = verdict_for(fixture.raw, corpus, institutions)
        if analysis.verdict.verified != fixture.expected_verified:
            failures.append(
                f"{fixture.name}: expected verified={fixture.expected_verified}, "
                f"got {analysis.verdict.verified} "
                f"({analysis.verdict.failure_reason})"
            )
    assert not failures, "\n".join(failures)


def test_l_tag_is_a_hard_fail(corpus, institutions):
    """With l=, only the first N body bytes are signed and anything can be
    appended below. That is a failure, not a warning."""
    analysis = verdict_for(corpus.by_name("l-tag-appended").raw, corpus, institutions)
    assert analysis.verdict.verified is False
    assert analysis.verdict.l_tag_present is True
    assert "l=" in (analysis.verdict.failure_reason or "")


def test_one_flipped_byte_breaks_the_body_hash(corpus, institutions):
    analysis = verdict_for(corpus.by_name("tampered-body").raw, corpus, institutions)
    assert analysis.verdict.verified is False
    assert analysis.verdict.body_hash_matched is False
    assert "body hash" in (analysis.verdict.failure_reason or "").lower()


def test_a_forwarders_signature_buys_nothing(corpus, institutions):
    """Gmail's signature on a forward proves Gmail handled it. An allocator
    cannot spend that."""
    analysis = verdict_for(corpus.by_name("forwarded-broken").raw, corpus, institutions)
    assert analysis.verdict.verified is False

    ignored = [s for s in analysis.summaries if not s.considered]
    assert ignored, "the forwarder's signature should be listed and dismissed"
    assert any("not a known institution" in (s.reason or "") for s in ignored)


def test_valid_signature_from_an_unknown_domain_is_not_enough(corpus, institutions):
    analysis = verdict_for(corpus.by_name("unknown-domain").raw, corpus, institutions)
    assert analysis.verdict.verified is False
    assert "known institution" in (analysis.verdict.failure_reason or "")


class TestKeyRotation:
    """The argument for anchoring the captured key, stated as a test.

    A signature we can verify today is unverifiable in a year once the selector
    is retired — unless somebody wrote the key down at the time.
    """

    def test_retired_selector_cannot_be_verified_from_live_dns(self, corpus, institutions):
        archived = corpus.by_name("archived-retired-selector")
        analysis = verdict_for(archived.raw, corpus, institutions, records=corpus.live_dns)
        assert analysis.verdict.verified is False
        assert "retired" in (analysis.verdict.failure_reason or "")

    def test_the_captured_record_still_verifies_it(self, corpus, institutions):
        archived = corpus.by_name("archived-retired-selector")
        analysis = verdict_for(archived.raw, corpus, institutions)
        assert analysis.verdict.verified is True
        assert analysis.verdict.dns_txt_record is not None
        assert analysis.verdict.dns_captured_at == NOW

    def test_the_captured_record_is_committed_by_hash(self, corpus, institutions):
        analysis = verdict_for(
            corpus.by_name("archived-retired-selector").raw, corpus, institutions
        )
        form = analysis.verdict.canonical_form()
        assert form["dns_record_hash"] == analysis.verdict.dns_record_hash
        # The key itself is not in the leaf; its hash is. The record lives in
        # the database and travels in the export bundle.
        assert "dns_txt_record" not in form


def test_verification_never_touches_the_network(corpus, institutions, monkeypatch):
    """`core` is pure. If a DNS lookup ever crept into the verifier, this test
    would be the thing that noticed."""
    import socket

    def explode(*args, **kwargs):
        raise AssertionError("core.dkim attempted a network call")

    monkeypatch.setattr(socket, "socket", explode)
    monkeypatch.setattr(socket, "getaddrinfo", explode)

    analysis = verdict_for(corpus.by_name("statement-2026-07").raw, corpus, institutions)
    assert analysis.verdict.verified is True


def test_parser_finds_every_signature_and_its_lookup_name(corpus):
    raw = corpus.by_name("forwarded-broken").raw
    found = signatures(raw)
    assert len(found) == 2
    names = required_dns_names(raw)
    assert len(names) == 2
    assert all("._domainkey." in name for name in names)


@pytest.mark.parametrize("name", ["statement-2025-08", "statement-2026-07", "trade-confirmation"])
def test_signed_headers_cover_from(corpus, institutions, name):
    analysis = verdict_for(corpus.by_name(name).raw, corpus, institutions)
    assert "from" in analysis.verdict.signed_headers
