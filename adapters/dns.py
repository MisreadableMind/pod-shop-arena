"""DNS lookups, kept outside the verifier.

This is the only place that touches a resolver. `core.dkim` takes records as
arguments, which is what lets the same code verify a live message today and an
archived one in ten years from a record captured at the time.

Capturing is the point. A DKIM selector is retired eventually — that is normal
key hygiene, not misbehaviour — and when it goes, every signature under it
becomes unverifiable to anyone who did not write the key down. So we write it
down at first sight and commit its hash to the chain.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Protocol

import dns.exception
import dns.rdatatype
import dns.resolver

from adapters.config import settings


class DnsResolver(Protocol):
    def txt(self, names: Iterable[str]) -> dict[str, str]: ...


class LiveResolver:
    """Real DNS. Failure is a normal outcome, not an exception to propagate:
    a missing key means "we cannot verify this", which is a verdict."""

    def __init__(self, timeout: float | None = None) -> None:
        self.timeout = timeout if timeout is not None else settings().dns_timeout_seconds

    def txt(self, names: Iterable[str]) -> dict[str, str]:
        resolver = dns.resolver.Resolver()
        resolver.timeout = self.timeout
        resolver.lifetime = self.timeout

        found: dict[str, str] = {}
        for name in names:
            try:
                answer = resolver.resolve(name, dns.rdatatype.TXT)
            except (dns.exception.DNSException, ValueError):
                continue
            for record in answer:
                # A TXT record longer than 255 bytes arrives as several strings
                # that must be joined with no separator. RSA public keys are
                # always longer than 255 bytes, so getting this wrong breaks
                # every lookup rather than a rare one.
                joined = b"".join(record.strings).decode("utf-8", errors="replace")
                if "p=" in joined:
                    found[name] = joined
                    break
        return found


class StaticResolver:
    """A fixed map of records. Used by the fixture corpus, by tests, and by the
    standalone verifier, which reads captured records off disk."""

    def __init__(self, records: Mapping[str, str]) -> None:
        self.records = dict(records)

    def txt(self, names: Iterable[str]) -> dict[str, str]:
        return {name: self.records[name] for name in names if name in self.records}


class ChainResolver:
    """Try each resolver in turn.

    Live DNS first, then whatever we captured before. That order matters: a live
    lookup that succeeds is fresh evidence, and the fallback exists precisely
    for the selectors that have already gone.
    """

    def __init__(self, *resolvers: DnsResolver) -> None:
        self.resolvers = resolvers

    def txt(self, names: Iterable[str]) -> dict[str, str]:
        remaining = list(names)
        found: dict[str, str] = {}
        for resolver in self.resolvers:
            if not remaining:
                break
            found.update(resolver.txt(remaining))
            remaining = [name for name in remaining if name not in found]
        return found
