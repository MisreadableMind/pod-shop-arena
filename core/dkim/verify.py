"""Verifying a signature without touching the network.

The DNS record is an *argument*, not something this module goes and fetches.
That single choice buys three things: `core` stays pure and testable, the same
function verifies a live message and a five-year-old archived one, and an
allocator running our standalone verifier gets bit-identical behaviour from a
captured record with no DNS at all.

Verification is therefore two steps. `parse.required_dns_names` says what to
look up, an adapter looks it up, and this function judges.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

import dkim as dkimpy

from core.dkim.parse import SignatureInfo, signatures
from core.types import DkimVerdict, Institution

# RFC 6376 requires From to be covered. A signature that leaves it out lets
# anyone re-address the mail and keep the signature intact.
REQUIRED_SIGNED_HEADERS = ("from",)


@dataclass(frozen=True, slots=True)
class SignatureSummary:
    """What we made of one signature. Kept even for signatures we ignore, so
    the UI can show *why* Gmail's signature on a forward bought nothing."""

    index: int
    domain: str | None
    selector: str | None
    algorithm: str | None
    l_tag_present: bool
    considered: bool
    verified: bool
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "domain": self.domain,
            "selector": self.selector,
            "algorithm": self.algorithm,
            "l_tag_present": self.l_tag_present,
            "considered": self.considered,
            "verified": self.verified,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class DkimAnalysis:
    verdict: DkimVerdict
    institution: Institution | None
    summaries: tuple[SignatureSummary, ...]

    @property
    def verified(self) -> bool:
        return self.verdict.verified


def _dnsfunc(record: str):
    def lookup(name, timeout=5):  # signature must match dkimpy's expectation
        return record.encode("utf-8")

    return lookup


def _match_institution(
    sig: SignatureInfo, institutions: Sequence[Institution]
) -> Institution | None:
    if not sig.domain:
        return None
    for inst in institutions:
        if inst.signs_for(sig.domain):
            return inst
    return None


def _attempt(
    raw: bytes, sig: SignatureInfo, record: str
) -> tuple[bool, bool, str | None]:
    """Run the actual cryptography. Returns (verified, body_hash_matched, reason)."""
    try:
        verifier = dkimpy.DKIM(raw, minkey=1024)
        ok = verifier.verify(idx=sig.index, dnsfunc=_dnsfunc(record))
    except dkimpy.ValidationError as exc:
        text = str(exc)
        # dkimpy distinguishes these, and the difference matters to a reader:
        # a body hash mismatch means the content changed after signing.
        if "body hash" in text.lower():
            return False, False, f"body hash mismatch — content changed after signing ({text})"
        return False, True, f"signature did not validate ({text})"
    except dkimpy.KeyFormatError as exc:
        return False, False, f"DNS key is not a usable DKIM record ({exc})"
    except dkimpy.MessageFormatError as exc:
        return False, False, f"message is not well-formed for verification ({exc})"
    except dkimpy.DKIMException as exc:
        return False, False, f"verification failed ({exc})"

    if ok:
        return True, True, None
    return False, False, "signature did not validate"


def verify_message(
    raw: bytes,
    *,
    dns_records: Mapping[str, str],
    institutions: Sequence[Institution],
    captured_at: datetime,
) -> DkimAnalysis:
    """Judge a message against captured DNS keys.

    `dns_records` maps `<selector>._domainkey.<domain>` to the TXT record as it
    stood when we looked. Storing that record is what keeps this checkable after
    the selector is retired, which is most of the reason the chain earns a place.
    """
    sigs = signatures(raw)
    if not sigs:
        return DkimAnalysis(
            verdict=_unverified("no DKIM-Signature header on this message"),
            institution=None,
            summaries=(),
        )

    summaries: list[SignatureSummary] = []
    candidates: list[tuple[SignatureInfo, Institution]] = []

    for sig in sigs:
        inst = _match_institution(sig, institutions)
        if inst is None:
            summaries.append(
                SignatureSummary(
                    index=sig.index,
                    domain=sig.domain,
                    selector=sig.selector,
                    algorithm=sig.algorithm,
                    l_tag_present=sig.body_length is not None,
                    considered=False,
                    verified=False,
                    reason=(
                        f"{sig.domain or 'unknown domain'} is not a known institution; "
                        "this signature proves that party handled the mail and nothing more"
                    ),
                )
            )
        else:
            candidates.append((sig, inst))

    if not candidates:
        seen = ", ".join(sorted({s.domain or "?" for s in sigs}))
        return DkimAnalysis(
            verdict=_unverified(
                f"no signature from a known institution domain (saw: {seen})"
            ),
            institution=None,
            summaries=tuple(summaries),
        )

    fallback: DkimVerdict | None = None
    fallback_inst: Institution | None = None

    for sig, inst in candidates:
        l_present = sig.body_length is not None
        reason: str | None = None

        if l_present:
            # Hard fail, not a warning. With l= only the first N bytes of the
            # body are signed and anything can be appended below it.
            reason = (
                f"l= tag present (l={sig.body_length}): only the first bytes of the "
                "body are signed, so content can be appended below the signature"
            )
        elif missing := [
            h for h in REQUIRED_SIGNED_HEADERS if h not in sig.signed_headers
        ]:
            reason = f"signature does not cover required header(s): {', '.join(missing)}"

        record = dns_records.get(sig.dns_name or "")

        if reason is None and record is None:
            reason = (
                f"no DNS key captured for {sig.dns_name} — the selector may have "
                "been retired, which is why we capture the record at first sight"
            )

        if reason is not None:
            summaries.append(
                SignatureSummary(
                    index=sig.index,
                    domain=sig.domain,
                    selector=sig.selector,
                    algorithm=sig.algorithm,
                    l_tag_present=l_present,
                    considered=True,
                    verified=False,
                    reason=reason,
                )
            )
            if fallback is None:
                fallback = DkimVerdict(
                    verified=False,
                    d_domain=sig.domain,
                    selector=sig.selector,
                    algo=sig.algorithm,
                    l_tag_present=l_present,
                    dns_txt_record=record,
                    dns_captured_at=captured_at if record else None,
                    body_hash_matched=False,
                    signed_headers=sig.signed_headers,
                    failure_reason=reason,
                )
                fallback_inst = inst
            continue

        assert record is not None
        verified, body_ok, failure = _attempt(raw, sig, record)

        summaries.append(
            SignatureSummary(
                index=sig.index,
                domain=sig.domain,
                selector=sig.selector,
                algorithm=sig.algorithm,
                l_tag_present=False,
                considered=True,
                verified=verified,
                reason=failure,
            )
        )

        verdict = DkimVerdict(
            verified=verified,
            d_domain=sig.domain,
            selector=sig.selector,
            algo=sig.algorithm,
            l_tag_present=False,
            dns_txt_record=record,
            dns_captured_at=captured_at,
            body_hash_matched=body_ok,
            signed_headers=sig.signed_headers,
            failure_reason=failure,
        )

        if verified:
            return DkimAnalysis(
                verdict=verdict, institution=inst, summaries=tuple(summaries)
            )
        if fallback is None:
            fallback, fallback_inst = verdict, inst

    assert fallback is not None
    return DkimAnalysis(
        verdict=fallback, institution=fallback_inst, summaries=tuple(summaries)
    )


def _unverified(reason: str) -> DkimVerdict:
    return DkimVerdict(
        verified=False,
        d_domain=None,
        selector=None,
        algo=None,
        l_tag_present=False,
        dns_txt_record=None,
        dns_captured_at=None,
        body_hash_matched=False,
        failure_reason=reason,
    )
