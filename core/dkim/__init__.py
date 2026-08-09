"""DKIM: the institution's own key vouching for bytes it signed years ago
without thinking about it.

Split deliberately into `parse` (what does this message claim?) and `verify`
(is the claim true, given this key?), with the DNS lookup living outside both.
"""

from core.dkim.parse import (
    SignatureInfo,
    parse_tags,
    required_dns_names,
    signatures,
)
from core.dkim.verify import DkimAnalysis, SignatureSummary, verify_message

__all__ = [
    "DkimAnalysis",
    "SignatureInfo",
    "SignatureSummary",
    "parse_tags",
    "required_dns_names",
    "signatures",
    "verify_message",
]
