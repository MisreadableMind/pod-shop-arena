"""Reading DKIM-Signature headers out of raw message bytes.

Headers are parsed by hand rather than through `email.parser` on purpose. The
whole proof rests on the bytes being exactly what arrived — CRLF and all — and
the cheapest way to guarantee we never hand a re-serialized message to the
verifier is to never build one. This module only ever *reads*.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SignatureInfo:
    """One DKIM-Signature header, unpacked but not judged."""

    index: int
    domain: str | None  # d=
    selector: str | None  # s=
    algorithm: str | None  # a=
    body_length: int | None  # l=  -- the dangerous one
    body_hash: str | None  # bh=
    signed_headers: tuple[str, ...]  # h=
    canonicalization: str | None  # c=
    tags: dict[str, str]

    @property
    def dns_name(self) -> str | None:
        if not self.selector or not self.domain:
            return None
        return f"{self.selector}._domainkey.{self.domain}"


def split_header_block(raw: bytes) -> bytes:
    """Everything up to (not including) the blank line that ends the headers."""
    for terminator in (b"\r\n\r\n", b"\n\n"):
        idx = raw.find(terminator)
        if idx != -1:
            return raw[:idx]
    return raw


def unfold_headers(raw: bytes) -> list[tuple[str, str]]:
    """Return (name, value) pairs with continuation lines joined.

    RFC 5322 folding puts a header's value across several lines, each
    continuation starting with whitespace. Unfolding is a read-only operation
    on our copy; the stored blob is untouched.
    """
    block = split_header_block(raw)
    text = block.decode("utf-8", errors="replace")
    lines = text.replace("\r\n", "\n").split("\n")

    headers: list[tuple[str, str]] = []
    current_name: str | None = None
    current_value: list[str] = []

    def flush() -> None:
        if current_name is not None:
            headers.append((current_name, "".join(current_value)))

    for line in lines:
        if line[:1] in (" ", "\t") and current_name is not None:
            current_value.append(line)
            continue
        flush()
        if ":" in line:
            name, _, value = line.partition(":")
            current_name = name.strip()
            current_value = [value]
        else:
            current_name = None
            current_value = []
    flush()
    return headers


def parse_tags(value: str) -> dict[str, str]:
    """DKIM tag-value lists: `v=1; a=rsa-sha256; d=example.com; ...`

    Whitespace inside a value is stripped because folding may have inserted it
    mid-base64 — that is normal and expected, not tampering.
    """
    tags: dict[str, str] = {}
    for part in value.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, _, val = part.partition("=")
        tags[key.strip()] = "".join(val.split())
    return tags


def signatures(raw: bytes) -> list[SignatureInfo]:
    """Every DKIM-Signature on the message, in header order.

    Order matters: `dkimpy` addresses signatures by index counted the same way.
    """
    found: list[SignatureInfo] = []
    idx = 0
    for name, value in unfold_headers(raw):
        if name.lower() != "dkim-signature":
            continue
        tags = parse_tags(value)

        body_length: int | None = None
        if "l" in tags:
            try:
                body_length = int(tags["l"])
            except ValueError:
                body_length = -1  # present but unparseable; still disqualifying

        signed = tuple(
            h.strip().lower() for h in tags.get("h", "").split(":") if h.strip()
        )

        found.append(
            SignatureInfo(
                index=idx,
                domain=(tags.get("d") or "").lower().rstrip(".") or None,
                selector=tags.get("s") or None,
                algorithm=tags.get("a") or None,
                body_length=body_length,
                body_hash=tags.get("bh") or None,
                signed_headers=signed,
                canonicalization=tags.get("c") or None,
                tags=tags,
            )
        )
        idx += 1
    return found


def required_dns_names(raw: bytes) -> list[str]:
    """Which DNS records an adapter must fetch before we can verify anything.

    Parsing has to happen before the lookup, which is why verification is two
    steps: plan the lookups here, resolve them in an adapter, then verify purely.
    """
    names: list[str] = []
    for sig in signatures(raw):
        name = sig.dns_name
        if name and name not in names:
            names.append(name)
    return names
