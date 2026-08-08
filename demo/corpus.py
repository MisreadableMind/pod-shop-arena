"""A signed fixture corpus we control end to end.

These messages are synthetic and the repo says so everywhere it shows them. We
cannot obtain a real Interactive Brokers signature to commit to a public repo,
and forging one against the real `interactivebrokers.com` domain would be both
dishonest and useless — anyone checking live DNS would catch it in a second. So
the corpus signs for `ibkr-demo.podarena.test`, a domain that plainly does not
exist, using a keypair generated at build time.

What the corpus is genuinely good for is the part that matters: every message
below is signed with real RSA and verified by the real verifier, so the five
ways DKIM breaks are exercised against actual cryptography rather than mocked.

The interesting fixture is `archived`. It is signed with a selector that is
absent from live DNS — the situation every signature ends up in eventually —
and it still verifies against the record we captured at first sight. That is the
argument for anchoring the capture, made concrete.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import dkim as dkimpy
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from core.extractors.ibkr import INSTITUTION as IBKR
from core.types import Institution

DEMO_DOMAIN = "ibkr-demo.podarena.test"
FORWARDER_DOMAIN = "mail-forwarder.podarena.test"

CURRENT_SELECTOR = "blitz2026"
RETIRED_SELECTOR = "legacy2024"

ACCOUNT_REF = "U4471902"
BASE_CURRENCY = "USD"


def demo_institutions() -> tuple[Institution, ...]:
    """IBKR, plus the demo domain, for deployments running the fixture corpus.

    Kept out of `core.extractors` on purpose: the real allow-list should not
    grow a test domain just because a demo needs one.
    """
    return (
        Institution(
            id=IBKR.id,
            name=IBKR.name,
            domains=IBKR.domains + (DEMO_DOMAIN,),
            doc_types=IBKR.doc_types,
        ),
    )


# -- keys -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Keypair:
    private_pem: bytes
    dns_record: str


def make_keypair(bits: int = 2048) -> Keypair:
    key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_der = key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    record = "v=DKIM1; k=rsa; p=" + base64.b64encode(public_der).decode("ascii")
    return Keypair(private_pem=private_pem, dns_record=record)


# -- message bodies -------------------------------------------------------

_STYLE = (
    "font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;"
    "font-size:13px;color:#111"
)


def _trade_confirmation_html(trades: list[tuple[str, date, Decimal, Decimal, Decimal]]) -> str:
    rows = []
    for symbol, when, qty, price, commission in trades:
        proceeds = (-qty * price).quantize(Decimal("0.01"))
        rows.append(
            "<tr>"
            f"<td>{BASE_CURRENCY}</td>"
            f"<td>{symbol}</td>"
            f"<td>{when.isoformat()}, 14:31:07</td>"
            f"<td>{qty:+,}</td>"
            f"<td>{price:,.4f}</td>"
            f"<td>{proceeds:,.2f}</td>"
            f"<td>{commission:,.2f}</td>"
            "</tr>"
        )
    return f"""<html><body style="{_STYLE}">
<h2>Trade Confirmation</h2>
<p>Interactive Brokers &middot; Account {ACCOUNT_REF} &middot; Base Currency: {BASE_CURRENCY}</p>
<table border="1" cellpadding="4" cellspacing="0">
<tr><th>Currency</th><th>Symbol</th><th>Date/Time</th><th>Quantity</th>
<th>T. Price</th><th>Proceeds</th><th>Comm/Fee</th></tr>
{"".join(rows)}
</table>
<p>This confirmation is furnished pursuant to SEC Rule 10b-10.</p>
</body></html>"""


def _statement_html(period_end: date, nav: Decimal, flows: list[tuple[date, Decimal, str]]) -> str:
    flow_rows = "".join(
        "<tr>"
        f"<td>{BASE_CURRENCY}</td>"
        f"<td>{when.isoformat()}</td>"
        f"<td>{label}</td>"
        f"<td>{amount:,.2f}</td>"
        "</tr>"
        for when, amount, label in flows
    )
    flows_table = (
        f"""<h3>Deposits &amp; Withdrawals</h3>
<table border="1" cellpadding="4" cellspacing="0">
<tr><th>Currency</th><th>Settle Date</th><th>Description</th><th>Amount</th></tr>
{flow_rows}
</table>"""
        if flows
        else ""
    )
    return f"""<html><body style="{_STYLE}">
<h2>Activity Statement</h2>
<p>Interactive Brokers &middot; Account {ACCOUNT_REF} &middot; Base Currency: {BASE_CURRENCY}</p>
<p>Period : {period_end.replace(day=1).strftime("%B %-d, %Y")} - {period_end.strftime("%B %-d, %Y")}</p>
<h3>Net Asset Value</h3>
<table border="1" cellpadding="4" cellspacing="0">
<tr><th>Asset Class</th><th>Prior Total</th><th>Current Total</th></tr>
<tr><td>Stocks</td><td>-</td><td>{nav:,.2f}</td></tr>
<tr><td>Total</td><td>-</td><td>{nav:,.2f}</td></tr>
</table>
{flows_table}
</body></html>"""


def _message(subject: str, html: str, sent: datetime, sender_domain: str) -> bytes:
    """Raw RFC822 bytes with CRLF endings, built by hand.

    Not `email.message.EmailMessage`: the generator normalizes line endings and
    re-wraps headers, and a signature taken over the result would be a signature
    over something the recipient never saw.
    """
    headers = [
        f"From: Interactive Brokers <noreply@{sender_domain}>",
        "To: Ops <ops@podarena.app>",
        f"Subject: {subject}",
        f"Date: {sent.strftime('%a, %d %b %Y %H:%M:%S %z')}",
        f"Message-ID: <{sent.strftime('%Y%m%d%H%M%S')}.{abs(hash(subject)) % 10**8}@{sender_domain}>",
        "MIME-Version: 1.0",
        'Content-Type: text/html; charset="utf-8"',
        "Content-Transfer-Encoding: 8bit",
    ]
    return ("\r\n".join(headers) + "\r\n\r\n" + html.replace("\n", "\r\n")).encode("utf-8")


def _sign(
    message: bytes,
    keypair: Keypair,
    *,
    domain: str,
    selector: str,
    length: bool = False,
) -> bytes:
    signature = dkimpy.sign(
        message,
        selector.encode("ascii"),
        domain.encode("ascii"),
        keypair.private_pem,
        include_headers=[b"from", b"to", b"subject", b"date", b"message-id"],
        canonicalize=(b"relaxed", b"simple"),
        length=length,
    )
    return signature + message


# -- the corpus -----------------------------------------------------------


@dataclass
class Fixture:
    name: str
    filename: str
    raw: bytes
    expected_verified: bool
    expectation: str
    doc_kind: str = "statement"


@dataclass
class Corpus:
    fixtures: list[Fixture] = field(default_factory=list)
    captured_dns: dict[str, str] = field(default_factory=dict)
    live_dns: dict[str, str] = field(default_factory=dict)

    def by_name(self, name: str) -> Fixture:
        for fixture in self.fixtures:
            if fixture.name == name:
                return fixture
        raise KeyError(name)

    def write(self, outdir: Path) -> Path:
        outdir.mkdir(parents=True, exist_ok=True)
        for fixture in self.fixtures:
            (outdir / fixture.filename).write_bytes(fixture.raw)
        (outdir / "captured_dns.json").write_text(
            json.dumps(self.captured_dns, indent=2, sort_keys=True) + "\n"
        )
        (outdir / "live_dns.json").write_text(
            json.dumps(self.live_dns, indent=2, sort_keys=True) + "\n"
        )
        (outdir / "manifest.json").write_text(
            json.dumps(
                [
                    {
                        "name": f.name,
                        "file": f.filename,
                        "expected_verified": f.expected_verified,
                        "expectation": f.expectation,
                        "kind": f.doc_kind,
                    }
                    for f in self.fixtures
                ],
                indent=2,
            )
            + "\n"
        )
        return outdir


def _month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


# A twelve-month NAV path with a real drawdown in it, so max drawdown and
# Sortino have something to bite on rather than a straight line up.
_NAV_PATH: list[tuple[int, int, str, list[tuple[int, str, str]]]] = [
    (2025, 8, "12480000.00", []),
    (2025, 9, "12915400.00", []),
    (2025, 10, "13402750.00", [(15, "2000000.00", "Deposit")]),
    (2025, 11, "13108220.00", []),
    (2025, 12, "13744910.00", []),
    (2026, 1, "14320880.00", []),
    (2026, 2, "13615330.00", []),  # drawdown starts
    (2026, 3, "12988470.00", []),
    (2026, 4, "13571040.00", [(9, "-1500000.00", "Withdrawal")]),
    (2026, 5, "14226690.00", []),
    (2026, 6, "14905120.00", []),
    (2026, 7, "15488330.00", []),
]

_TRADES: list[tuple[str, date, Decimal, Decimal, Decimal]] = [
    ("AAPL", date(2026, 7, 14), Decimal("12000"), Decimal("214.8250"), Decimal("-38.40")),
    ("MSFT", date(2026, 7, 14), Decimal("-4500"), Decimal("501.1100"), Decimal("-21.15")),
    ("NVDA", date(2026, 7, 15), Decimal("8000"), Decimal("182.4750"), Decimal("-29.60")),
]


def build_corpus() -> Corpus:
    """Generate keys, sign the messages, and record what DNS said at the time."""
    current = make_keypair()
    retired = make_keypair()
    forwarder = make_keypair()

    captured = {
        f"{CURRENT_SELECTOR}._domainkey.{DEMO_DOMAIN}": current.dns_record,
        f"{RETIRED_SELECTOR}._domainkey.{DEMO_DOMAIN}": retired.dns_record,
        f"fwd._domainkey.{FORWARDER_DOMAIN}": forwarder.dns_record,
    }
    # Live DNS has moved on: the retired selector is simply gone. This is the
    # normal end state of every DKIM key, and the reason a capture is worth
    # committing to a chain.
    live = {
        f"{CURRENT_SELECTOR}._domainkey.{DEMO_DOMAIN}": current.dns_record,
        f"fwd._domainkey.{FORWARDER_DOMAIN}": forwarder.dns_record,
    }

    corpus = Corpus(captured_dns=captured, live_dns=live)

    # Twelve signed monthly statements: the actual track record.
    for year, month, nav, flows in _NAV_PATH:
        period_end = _month_end(year, month)
        flow_rows = [
            (date(year, month, day), Decimal(amount), label)
            for day, amount, label in flows
        ]
        sent = datetime(year, month, 28, 6, 5, 0, tzinfo=timezone.utc)
        if period_end.day < 28:
            sent = datetime.combine(period_end, sent.time()).replace(tzinfo=timezone.utc)
        message = _message(
            f"Activity Statement — {period_end.strftime('%B %Y')}",
            _statement_html(period_end, Decimal(nav), flow_rows),
            sent,
            DEMO_DOMAIN,
        )
        corpus.fixtures.append(
            Fixture(
                name=f"statement-{year}-{month:02d}",
                filename=f"statement-{year}-{month:02d}.eml",
                raw=_sign(message, current, domain=DEMO_DOMAIN, selector=CURRENT_SELECTOR),
                expected_verified=True,
                expectation="valid signature over NAV and flows",
            )
        )

    # A trade confirmation — the first extractor's real target.
    confirmation = _message(
        "Trade Confirmation — 15 July 2026",
        _trade_confirmation_html(_TRADES),
        datetime(2026, 7, 15, 21, 2, 0, tzinfo=timezone.utc),
        DEMO_DOMAIN,
    )
    signed_confirmation = _sign(
        confirmation, current, domain=DEMO_DOMAIN, selector=CURRENT_SELECTOR
    )
    corpus.fixtures.append(
        Fixture(
            name="trade-confirmation",
            filename="trade-confirmation.eml",
            raw=signed_confirmation,
            expected_verified=True,
            expectation="valid signature over three fills",
            doc_kind="trade_confirmation",
        )
    )

    # 1. Archived: signed with a selector that has since left DNS. Verifies
    #    against the captured record and against nothing else.
    archived = _message(
        "Activity Statement — July 2024",
        _statement_html(date(2024, 7, 31), Decimal("9120400.00"), []),
        datetime(2024, 7, 31, 6, 5, 0, tzinfo=timezone.utc),
        DEMO_DOMAIN,
    )
    corpus.fixtures.append(
        Fixture(
            name="archived-retired-selector",
            filename="archived-retired-selector.eml",
            raw=_sign(archived, retired, domain=DEMO_DOMAIN, selector=RETIRED_SELECTOR),
            expected_verified=True,
            expectation="verifies only from the captured DNS record; the selector "
            "is absent from live DNS",
        )
    )

    # 2. l= tag: only the first N body bytes are signed, so anything can be
    #    appended below. Hard fail, not a warning.
    truncatable = _message(
        "Activity Statement — June 2026 (partial coverage)",
        _statement_html(date(2026, 6, 30), Decimal("14905120.00"), []),
        datetime(2026, 6, 30, 6, 5, 0, tzinfo=timezone.utc),
        DEMO_DOMAIN,
    )
    signed_l = _sign(
        truncatable, current, domain=DEMO_DOMAIN, selector=CURRENT_SELECTOR, length=True
    )
    corpus.fixtures.append(
        Fixture(
            name="l-tag-appended",
            filename="l-tag-appended.eml",
            raw=signed_l + b"\r\n<p>Net Asset Value: 99,000,000.00</p>\r\n",
            expected_verified=False,
            expectation="l= tag present; content appended below the signed prefix",
        )
    )

    # 3. Tampered: one digit of the NAV changed after signing. Same length, so
    #    only the body hash catches it.
    tampered = signed_confirmation.replace(b"214.8250", b"274.8250", 1)
    assert tampered != signed_confirmation, "tamper fixture did not change anything"
    corpus.fixtures.append(
        Fixture(
            name="tampered-body",
            filename="tampered-body.eml",
            raw=tampered,
            expected_verified=False,
            expectation="one price digit altered after signing; body hash must fail",
            doc_kind="trade_confirmation",
        )
    )

    # 4. Forwarded by hand: the client rewrote the body, so the institution's
    #    signature is broken. The forwarder's own signature is intact and worth
    #    nothing, which is the point of the fixture.
    forwarded_body = _statement_html(date(2026, 5, 31), Decimal("14226690.00"), [])
    forwarded_message = _message(
        "Fwd: Activity Statement — May 2026",
        "<p>---------- Forwarded message ----------</p>" + forwarded_body,
        datetime(2026, 6, 1, 9, 14, 0, tzinfo=timezone.utc),
        FORWARDER_DOMAIN,
    )
    broken_institution_sig = _sign(
        _message(
            "Fwd: Activity Statement — May 2026",
            forwarded_body,  # what was signed
            datetime(2026, 6, 1, 9, 14, 0, tzinfo=timezone.utc),
            FORWARDER_DOMAIN,
        ),
        current,
        domain=DEMO_DOMAIN,
        selector=CURRENT_SELECTOR,
    )
    institution_header = broken_institution_sig.split(b"\r\n\r\n")[0].split(
        b"DKIM-Signature:"
    )[1]
    forwarded = _sign(
        b"DKIM-Signature:" + institution_header + b"\r\n" + forwarded_message,
        forwarder,
        domain=FORWARDER_DOMAIN,
        selector="fwd",
    )
    corpus.fixtures.append(
        Fixture(
            name="forwarded-broken",
            filename="forwarded-broken.eml",
            raw=forwarded,
            expected_verified=False,
            expectation="manual forward rewrote the body; the forwarder's signature "
            "verifies and proves only that the forwarder handled it",
        )
    )

    # 5. Unknown domain: a perfectly valid signature from somebody we have no
    #    reason to believe.
    stranger = _message(
        "Your portfolio update",
        _statement_html(date(2026, 7, 31), Decimal("99000000.00"), []),
        datetime(2026, 8, 1, 8, 0, 0, tzinfo=timezone.utc),
        FORWARDER_DOMAIN,
    )
    corpus.fixtures.append(
        Fixture(
            name="unknown-domain",
            filename="unknown-domain.eml",
            raw=_sign(stranger, forwarder, domain=FORWARDER_DOMAIN, selector="fwd"),
            expected_verified=False,
            expectation="valid signature, but not from a known institution domain",
        )
    )

    return corpus


def load_corpus(outdir: Path) -> Corpus | None:
    """Read a corpus written earlier, or None if there isn't one."""
    manifest_path = outdir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text())
        corpus = Corpus(
            captured_dns=json.loads((outdir / "captured_dns.json").read_text()),
            live_dns=json.loads((outdir / "live_dns.json").read_text()),
        )
        for entry in manifest:
            corpus.fixtures.append(
                Fixture(
                    name=entry["name"],
                    filename=entry["file"],
                    raw=(outdir / entry["file"]).read_bytes(),
                    expected_verified=entry["expected_verified"],
                    expectation=entry["expectation"],
                    doc_kind=entry.get("kind", "statement"),
                )
            )
        return corpus
    except (OSError, KeyError, ValueError):
        return None


def load_or_build(outdir: Path) -> Corpus:
    """Generate the corpus once, then reuse it.

    Regenerating on every boot would mint fresh keys, which means fresh bytes,
    which means fresh SHA-256s — and the pipeline would see every restart as a
    pile of brand new evidence rather than the same twelve statements. Writing
    it to the persistent disk keeps a deployment's fixtures stable across
    redeploys, which is what makes re-seeding a no-op.
    """
    existing = load_corpus(outdir)
    if existing is not None and existing.fixtures:
        return existing
    corpus = build_corpus()
    corpus.write(outdir)
    return corpus


def main() -> None:
    import sys

    outdir = Path(sys.argv[1] if len(sys.argv) > 1 else "var/fixtures")
    corpus = build_corpus()
    corpus.write(outdir)
    print(f"wrote {len(corpus.fixtures)} fixtures to {outdir}")
    for fixture in corpus.fixtures:
        mark = "verifies" if fixture.expected_verified else "fails   "
        print(f"  {mark}  {fixture.filename}")


if __name__ == "__main__":
    main()
