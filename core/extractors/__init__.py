"""The institutions whose signatures we will believe, and the code that reads
what they send.

Importing this module is what populates the extractor registry. The institution
list doubles as the DKIM allow-list: a `d=` outside it may be a perfectly valid
signature and still tell an allocator nothing, because it proves the forwarder
handled the mail rather than the broker vouching for the numbers.
"""

from __future__ import annotations

from core.extraction.base import registry
from core.extractors import ibkr, selfreported
from core.types import Institution

INSTITUTIONS: tuple[Institution, ...] = (ibkr.INSTITUTION,)

INSTITUTIONS_BY_ID: dict[str, Institution] = {inst.id: inst for inst in INSTITUTIONS}


def institution_for_domain(d_domain: str) -> Institution | None:
    for inst in INSTITUTIONS:
        if inst.signs_for(d_domain):
            return inst
    return None


__all__ = [
    "INSTITUTIONS",
    "INSTITUTIONS_BY_ID",
    "ibkr",
    "institution_for_domain",
    "registry",
    "selfreported",
]
