# Pod Arena — build plan

How the app actually works, and the order we build it in.

Companion docs: [`strategy.md`](./strategy.md) is why, this is how. The deck is
[`deck/index.html`](./deck/index.html).

---

## Context

A track record is worth nothing if the person it flatters typed it. Every existing fix
asks the institution to cooperate — an API, a data feed, a signed letter — and Goldman is
not going to cooperate. So the product has to work on evidence the institution *already*
emits without agreeing to anything, and it has to be honest about how strong that
evidence is.

Two things are being built, and conflating them is the main way this goes wrong:

**Authenticity** — did these bytes come from the institution? That's cryptography. A DKIM
signature on a statement email is the institution's own key vouching for the content, and
they signed it years ago without thinking about it.

**Integrity over time** — was this claimed before the claimer knew how the month would
turn out? That's the chain. Anchoring doesn't stop a lie; it stops a *later* lie. Commit
every ingest and backfilling dies, because the sequence is public and contiguous.

Everything below serves one of those two. If a feature serves neither, it's in §9.

---

## 1. The trust ladder

The tier is a property of **evidence**, never of a connector or a customer. It is
computed, never asserted.

| Tier | What it means | How we get it |
| --- | --- | --- |
| `source_signed` | The institution's own key verifies the bytes | DKIM on statement/confirmation email; signed PDF; zkTLS session transcript |
| `aggregator_attested` | A named third party pulled it | IBKR Flex, administrator SFTP, Plaid |
| `platform_observed` | We saw it. Our word only | Extension or agent capture |
| `self_reported` | Nobody vouches | CSV, manual entry |

Propagation rules, enforced in the pure core:

- A **fact** inherits the tier of the document it came from.
- A **metric** carries `min(tier)` over every fact that fed it. One CSV row in a
  twelve-month TWR drags the whole number to `self_reported`. That is correct and it is
  the point.
- Nothing is displayed without its tier next to it.

We are not building `platform_observed`. An agent logging in as the user buys no stronger
signature than Plaid does, and costs us credential custody, most brokers' ToS, and the
"read-only, never custody" principle. The rung exists in the model so the UI can grade
imported data honestly, not so we can ship a scraper.

---

## 2. Authenticity: the DKIM path

The differentiator, so it gets built properly.

### What DKIM actually gives us

A `DKIM-Signature` header signs a set of headers plus `bh=`, a hash of the body — MIME
attachments included. The public key lives in DNS at `<selector>._domainkey.<domain>`.
Verify it and you have proved: *these exact bytes left this domain*.

### The five things that break it

1. **Byte exactness.** Verification runs against the raw RFC822 bytes as received, CRLF
   and all. We store the original blob and verify against *that*, never against anything
   re-serialized by a mail library. Any pipeline stage that normalizes line endings
   silently destroys the proof.
2. **Key rotation.** Selectors get retired and leave DNS. A signature we can verify today
   is unverifiable in a year. **So we capture the DNS TXT record at first verification,
   store it with the document, and include its hash in what we anchor.** That timestamped
   capture is what makes the proof durable — and it's a concrete reason the chain earns
   its place.
3. **The `l=` tag.** If present, only the first N bytes of the body are signed and
   content can be appended below. Treat `l=` as a hard fail, not a warning.
4. **Multiple signatures.** A forwarded mail carries the forwarder's DKIM too. We only
   care about a signature whose `d=` is the institution's domain, matched against a
   registry of known institution domains. Gmail's signature on a forward proves Gmail
   handled it, which is worth nothing to an allocator.
5. **Forwarding.** Manual "Forward" from a mail client rewrites the body and breaks the
   signature. A server-side auto-forward *filter* usually preserves it.

### Intake channels

- **Per-entity ingest address** (`u_<id>@ingest.podarena.app`), and the manager sets a
  filter to auto-forward from their broker/administrator. Primary path.
- **`.eml` upload.** Always works, always intact. Fallback and the honest default.

### Authenticity is not interpretation

DKIM proves the bytes. It does not prove that "NAV: 41,207,338.22" means what our parser
thinks it means. So the two are modeled separately and both are shown:

- The signature verdict is cryptographic and final.
- The **extraction** is our code — versioned, pure, and reproducible. Anyone can pull the
  original signed document and check our reading.

Extractors are `(institution, doc_type, version) -> Fact[]`, pure functions with the
version recorded on every fact. When we fix a parser we bump the version and re-derive;
the original evidence never changes.

---

## 3. Architecture

Dependency runs one way. `core` is pure Python — no I/O, no clock, no network — because
that is what makes results reproducible and the determinism testable.

```
contracts/          Foundry. TrackRecordRegistry on Monad.
core/               Pure. Domain types, tier algebra, extraction interfaces,
                    metrics engine, Merkle. Depends on nothing.
adapters/           DNS, blob store, chain client, mail intake, IBKR Flex, SFTP.
api/                FastAPI. Auth, routes, and the fence (server-side projection).
worker/             arq tasks. The ingest pipeline.
web/                Vite + React + TanStack. viem for on-chain reads.
```

**Backend** — Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 + Alembic, `uv` for deps,
arq + Redis for the pipeline, `dkimpy` + `dnspython` for signatures, `web3.py` for
anchoring.

**Frontend** — React + Vite, TanStack Router / Query / Table / Form, **viem 2.40+** for
reading anchors straight from Monad. Charts are hand-rolled inline SVG so the picture and
the numbers can never disagree.

**Data** — Postgres 16 for structured state. Raw documents go to S3/R2 as
content-addressed write-once blobs, encrypted per entity. Never in the database.

Two rules that are load-bearing rather than stylistic:

- **Money is `BIGINT` minor units plus a currency code.** Never a float, anywhere.
- **Metrics compute in `Decimal`** with an explicit quantization step, so the same inputs
  give the same bytes on every machine. Float non-determinism would break the anchor.

---

## 4. Schema

```
entity            the manager or fund
account           a book at an institution; belongs to an entity
institution       name, domains[], known DKIM selectors, doc types we can parse

document          sha256, blob_key, received_at, channel, institution_id  (write-once)
dkim_verdict      document_id, d_domain, selector, verified, l_tag_present,
                  dns_txt_record, dns_captured_at, algo, failure_reason
extraction        document_id, extractor_version, status, payload jsonb
fact              account_id, document_id, as_of, kind, instrument, qty,
                  price_minor, amount_minor, currency, tier

snapshot          record_id, seq, fact_root, metrics_hash, methodology_version,
                  extractor_versions jsonb
metric_result     snapshot_id, key, value, formula, inputs, tier
finding           snapshot_id, kind, severity, detail        (reconciliation conflicts)

anchor            snapshot_id, chain_id, tx_hash, block_number, root, seq, confirmed_at
invite            record_id, viewer_email, profile, nda_version, token_hash,
                  expires_at, revoked_at
access_event      invite_id, action, at, ip, ua, chain_tx     (append-only)
```

`document` and `access_event` are append-only by convention *and* by a database trigger
that rejects `UPDATE`/`DELETE`. An audit trail you can quietly edit is not an audit trail.

---

## 5. The ingest pipeline

One orchestrator, numbered steps, each pure where it can be:

1. **Receive** — raw bytes land from mail intake or upload. Hash, write blob, insert
   `document`. Identical content is a no-op.
2. **Verify** — run DKIM against the raw bytes. Capture the DNS key. Write `dkim_verdict`.
   Assign the tier here and nowhere else.
3. **Extract** — pick the extractor by `(institution, doc_type)`, run it, store the
   payload and the version.
4. **Normalize** — extraction payload becomes `fact` rows, each pointing at its document
   and inheriting its tier.
5. **Reconcile** — where two sources cover the same period, they must agree. A mismatch
   writes a `finding`, it does not throw. Allocators care more about the discrepancies we
   surface than the ones we hide.
6. **Compute** — the pure metrics engine over the ordered fact series. Linked TWR,
   Modified Dietz across flows, max drawdown, volatility, Sharpe, Sortino, Calmar, VaR.
   Net *and* gross side by side, with the fee model an explicit input, because the SEC
   Marketing Rule requires it.
7. **Commit** — build the Merkle tree, anchor the root on Monad, store the `anchor` when
   the receipt confirms.

### What goes in the tree

Leaves, canonically serialized and sorted:

- each document's content hash
- each DKIM verdict, including the hash of the captured DNS key record
- each fact's canonical hash
- the metrics result hash, with methodology version and every extractor version

So the anchor commits to the evidence, to the proof that the evidence was signed, to our
reading of it, and to the code version that did the reading. All four, or the commitment
is a fig leaf.

---

## 6. Contract

```solidity
contract TrackRecordRegistry {
    event Anchored(bytes32 indexed recordId, bytes32 root, uint64 seq, uint64 ts);
    event Accessed(bytes32 indexed recordId, bytes32 viewerCommitment, uint8 profile, uint64 ts);

    function anchor(bytes32 recordId, bytes32 root) external returns (uint64 seq);
    function logAccess(bytes32 recordId, bytes32 viewerCommitment, uint8 profile) external;
    function head(bytes32 recordId) external view returns (bytes32 root, uint64 seq, uint64 ts);
}
```

Storage keeps only the head and a counter; history lives in events, which is far cheaper
and just as verifiable. `seq` is strictly monotonic per record, so a gap in the sequence
is visible to anyone reading the log — that is the anti-backfill mechanism.

`viewerCommitment` is `keccak(viewer_id ‖ per_record_salt)`. The chain shows *that* a view
happened and when, without publishing who. The salt is disclosed to the record owner only.

**Why Monad.** Anchoring every ingest and every view is only sensible at 0.3 s blocks and
0.6 s finality. On a twelve-second chain you batch nightly, and the moment you batch you
have proved the day rather than the moment — which is exactly the property worth having.

---

## 7. The fence

- **Invite** is bound to an identity and a disclosure profile, single-use, expiring,
  revocable. Not a public URL with a long random string.
- **NDA gate** renders before anything else; consent is written to `access_event` before
  the first byte of data is served.
- **Disclosure profile** is applied as a **server-side projection**. The filtered fields
  never enter the response, so there is no client-side toggle to defeat. This is the one
  security property to hold absolutely: hidden data does not cross the wire.
- **Watermark** with viewer identity and timestamp, composited server-side into any
  export as well as rendered client-side.
- **Access** is written to the audit log and committed on-chain.

Profiles: `summary` · `ratios_and_risk` · `full_detail` · `full_plus_positions`.
Default is metrics-only. Positions are opt-in, per viewer, every time.

---

## 8. Independent verification

The property we are actually selling is that **our API is never in the trust path.** In
the viewer's browser:

1. Read the anchored root from Monad with viem, through their RPC, not ours.
2. Fetch the Merkle path for the leaves the profile permits.
3. Re-fold and compare locally. Show `Verified locally` only when local math agrees.
4. Download any original signed document and re-run DKIM independently — we ship a
   standalone verifier that takes an `.eml` plus the captured DNS record and needs no
   Pod Arena account.

If we shut down tomorrow, an allocator holding the documents can still prove everything.
That is the standard to build to.

---

## 9. Order of work

Each phase ends with something demonstrable end to end.

**Phase 0 · Spine.** Monorepo, `core` with domain types and the tier algebra, Postgres +
Alembic, FastAPI skeleton, contract deployed to Monad Testnet, one route that anchors a
hard-coded root and reads it back. Proves the riskiest seam first.

**Phase 1 · Authenticity.** `.eml` upload, DKIM verification with DNS key capture, blob
store, the first extractor for one real institution, facts landing in Postgres with a
computed tier. This is the differentiator, so it comes before anything pretty.

**Phase 2 · Numbers.** The deterministic metrics engine, net and gross, provenance on
every value, reconciliation findings, and the determinism test that asserts same inputs →
same hash → same root.

**Phase 3 · Commitment.** Full Merkle tree over the four leaf classes, per-ingest
anchoring, the anchor timeline in the UI, in-browser re-folding, and the standalone
verifier.

**Phase 4 · The fence.** Invites, NDA gate, server-side projections, watermarking, audit
log, on-chain access commitments.

**Phase 5 · Reach.** Mail intake with per-entity addresses. IBKR Flex. Administrator
SFTP. Each drops in behind the existing evidence interface.

**Phase 6 · Later.** zkTLS for portals with no email and no feed. ZK proofs so a manager
proves 22% without showing a position. GIPS composites. Attribution.

### Not building

Retail broker connectors, discovery marketplace, reputation graph, peer cohorts, hiring
workflow, and any form of agent-logs-in scraping. The first five have no buyer today. The
last one is a liability dressed as a feature.

---

## 10. How we know it works

- **Determinism test.** Same fixture inputs produce the same fact hashes, the same metric
  values, and the same Merkle root, across machines and runs. This is the contract that
  makes everything else meaningful, so it is the test that must never be skipped.
- **DKIM fixtures.** A corpus of real signed messages: valid, `l=`-tagged, key-rotated,
  body-tampered by one byte, forwarded-and-broken. Each has an expected verdict.
- **Tamper test.** Flip a byte in a stored document; the verdict must fail, the tier must
  drop, the recomputed root must differ from the anchored one, and the UI must say so
  without being asked.
- **Projection test.** For every disclosure profile, assert the serialized response
  contains no field the profile forbids. Test the wire, not the component.
- **Anchor round-trip.** Anchor on Monad Testnet, then verify in a browser using a public
  RPC we do not control.
- **Cold-verify drill.** Hand someone the `.eml` files, the captured DNS records, and the
  contract address, with no access to our API. They should be able to prove the record
  themselves. If they can't, the design has failed regardless of what the tests say.
