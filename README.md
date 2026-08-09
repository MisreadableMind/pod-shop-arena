# PodShop Arena

**A portfolio manager's track record, proved with the broker's own signature and anchored on
Monad — checkable by an allocator who does not trust us and never asks our server
anything.**

---

## The idea

A track record is worth nothing if the person it flatters typed it. Every existing fix
asks the institution to cooperate — an API, a data feed, a signed letter — and Goldman is
not going to cooperate.

But your broker already signs things. Every statement email carries a DKIM signature:
the institution's own key, vouching for the exact bytes, applied years ago without anyone
thinking about it. Nobody has to agree to anything. The proof is already in your inbox.

Two separate jobs, and conflating them is how this goes wrong:

**DKIM proves the bytes came from the institution.** Cryptography. No chain needed.

**The chain proves nothing was added later.** Anchoring doesn't stop a lie; it stops a
*later* lie. Every ingest gets a sequence number, so a manager who quietly drops a bad
month leaves a gap anyone can read.

### Why the chain actually earns its place

Not "immutability" — that's the answer everyone gives and it's mostly decoration. Here it
is a specific mechanical problem:

**DKIM selectors get retired.** That's normal key hygiene. And when a key leaves DNS,
every signature made under it becomes unverifiable to anyone who didn't write the key down
at the time. A signature you can check today is unverifiable in a year.

So we capture the DNS TXT record at first verification, store it with the document, and
commit its hash on-chain. That timestamped capture is what keeps a five-year-old signature
checkable. There's a test for exactly this — `tests/test_dkim.py::TestKeyRotation` — where
an archived message fails against live DNS and verifies against the captured record.

**And why Monad specifically.** We anchor on every ingest and every view. That's only
sensible at 0.3s blocks and 0.6s finality. On a twelve-second chain you batch nightly, and
the moment you batch, you've proved *the day* rather than *the moment* — which is exactly
the property worth having, and exactly what a backfiller needs you to give up.

---

## Live

| | |
| --- | --- |
| **App** | https://PODARENA_URL_HERE — the staged demo, live |
| **Contract** | [`0xf56b105C35d9C7c443E829A24a6cAb014f9e8353`](https://testnet.monadvision.com/address/0xf56b105C35d9C7c443E829A24a6cAb014f9e8353) — `TrackRecordRegistry`, [deploy tx](https://testnet.monadvision.com/tx/0x9289228705b4de5871eb888420a1d272d2d2b59a2a1538305df4e48a7238ff37) in block 51986893 |
| **Chain** | Monad Testnet, id `10143`, RPC `https://testnet-rpc.monad.xyz` |
| **Explorer** | https://testnet.monadvision.com |

Three records are already staged there — open the allocator links in
[Demo credentials](#demo-credentials) and nothing needs typing. To run your own instance,
[Deploy](#deploy) takes about five minutes.

Without a contract address the app still computes and stores Merkle roots — it marks them
unanchored rather than pretending otherwise.

---

## Everything in the demo is synthetic, and says so

We cannot put a real Interactive Brokers signature in a public repo, and forging one
against the real `interactivebrokers.com` would be both dishonest and useless — anyone
checking live DNS catches it instantly.

So the fixture corpus signs for `ibkr-demo.podarena.test`, a domain that plainly does not
exist, using an RSA keypair generated when the instance is first built. **The cryptography
is real.** Every message is really signed, every verdict comes from the real verifier
running real RSA, and all five failure modes are exercised against actual signatures. The
broker is the only fake part.

---

## Three records, three arguments

The demo is staged, not typed. Each record makes exactly one point.

**`meridian-global-macro`** — twelve monthly statements, each signed by the broker's key.
Everything grades `source_signed`. Annualized TWR 21.89% net, 35.84% gross.

**`northwind-partners`** — the same twelve numbers. Eleven months signed; the twelfth typed
into a CSV. **`twr_annualized` is identical to the digit — `0.218937808100` — and the whole
record grades `self_reported`.** One row does it. A metric carries `min(tier)` over every
fact that fed it, so a single unverifiable month caps a year of proof. That will feel
punitive to a customer and it is exactly right.

**`evidence-lab`** — the five ways DKIM breaks, each a real signature with a real verdict:

| Fixture | Verdict |
| --- | --- |
| Retired selector | **Verifies** — from the captured record; live DNS can't do it |
| `l=` tag, content appended | **Fails** — only a prefix of the body was signed |
| One digit changed after signing | **Fails** — body hash mismatch |
| Hand-forwarded from a mail client | **Fails** — and the forwarder's own signature is shown being dismissed |
| Valid signature, unknown domain | **Fails** — proves that party handled the mail, nothing more |

---

## Three seats, and the walls between them

Nobody here sees the same product, and the differences *are* the product. A pod shop has
two people inside the wall and one outside it:

**The fund** is the platform. It signs in with the admin token, sees the whole roster,
and is the only seat that can take a new pod on.

**The portfolio manager** runs one book. Same console, one pod. They can't open the pod
next door — and the refusal is a `404`, not a `403`, because a refusal that distinguishes
*not yours* from *no such thing* leaks the roster one guess at a time. Their token is
`pm_<slug>_<mac>`, derived by HMAC from the fund's, so knowing yours tells you nothing
about anyone else's. `/api/me` filters the roster server-side: the names of the other
pods never reach a PM's machine to be hidden.

**The allocator** is outside the wall and never gets an account at all.

The manager's console — either seat — shows every metric at every basis, the evidence
with each DKIM verdict, the reconciliation findings, the anchor timeline — and, on the
same page, a **disclosure matrix**: one row per section of the payload, one column per
profile, showing what each allocator actually receives. The numbers in it are measured,
not asserted. Each column is the projection run for real and the response serialized, so
the byte count is the byte count:

| | Summary | Ratios & risk | Full detail | Full + positions |
| --- | ---: | ---: | ---: | ---: |
| Bytes on the wire | 4.0 kB | 11.0 kB | 36.7 kB | 37.4 kB |
| Metrics | 6 | 18 | 18 | 18 |
| Evidence documents | — | — | 13 | 13 |
| NAV series | — | — | 12 | 12 |
| Positions | — | — | — | 3 |

Click a column and the page renders exactly that payload, using the same components the
allocator's browser uses. Not a mock-up — one fetch against the same `project()` the
allocator path calls, so the preview and the real thing cannot drift.

An allocator never gets an account. They get one link, bound to their address and to
a profile, watermarked with their name, revocable mid-conversation. Their page states
which profile they are on and what that rung withholds, because a number withheld silently
is indistinguishable from a number that does not exist.

The wall is server-side and it fails closed: the response is *built up* from what a profile
permits rather than built in full and filtered down. A dash in that table means the key is
absent from the JSON. Opening dev tools finds nothing, because there is nothing to find.
`tests/test_projection.py` asserts it against the serialized payload for every profile;
`tests/test_owner_console.py` checks the matrix against the payloads it describes.

### Demo credentials

Sign-in is one click. `/manage` lists one button per seat — *Fund · all 3 pods*, then a
button per PM — and the buttons make the argument before you've even signed in.

| Seat | How you get in | Reach |
| --- | --- | --- |
| **Fund** | `/manage` → *Fund* | Every pod |
| **Portfolio manager** | `/manage` → *Meridian Global Macro* | That pod, nothing else |
| **Allocator** | `/view/demo-meridian-full` · `/view/demo-northwind-full` · `/view/demo-evidence-lab` · `/view/demo-meridian-summary` | One profile of one pod |

Open the fund seat, then a PM seat, and watch the roster disappear.

The last two links are the same fund, `meridian-global-macro`, seen through `full_detail`
and through `summary`. Open both.

`demo_admin_token` and the PM tokens are served **only** when `PODARENA_DEMO_FIXTURES=true`,
and an instance holding real evidence cannot run the synthetic corpus. Both halves of that
are tested.

---

## Verify it without us

That's the actual product. Two routes:

**In the browser.** The record page re-folds all 47 Merkle leaves locally with Web Crypto,
checks a server-supplied proof path against its own fold, and reads the anchored root off
Monad through **an RPC endpoint you type in**. It says *Verified locally* only when the
local maths agrees. Our API computes none of it.

**Offline.** Download the evidence bundle — the `.eml` files, the DNS keys exactly as
captured, every Merkle proof, the contract address — and run:

```bash
podarena-verify bundle ./meridian-global-macro-seq1.zip
```

Every check runs with no network and no account. The only thing it can't do offline is
read the chain, so it prints the `cast call` you should run against an RPC of your choice.

If the bundle ever disagrees with what our UI told you, believe the bundle.

---

## Run it locally

Needs Python 3.12 (via [uv](https://docs.astral.sh/uv/)) and Node 22.

```bash
uv sync
(cd web && npm install && npm run build)

export PODARENA_DATABASE_URL="sqlite:///var/dev.db"   # Postgres in production
export PODARENA_ADMIN_TOKEN="demo-manager-token"      # opens /manage; pick anything
uv run python -m adapters.bootstrap                   # schema + append-only triggers
uv run python -m demo.seed --reset --no-anchor        # generate the corpus, stage the demo
uv run uvicorn api.app:app --port 8000
```

Then open http://localhost:8000. The two doors are on the front page: `/manage` for the
manager — the login screen fills your token in — and the allocator links, which the seed
script also prints.

```bash
uv run pytest                                  # 99 tests
(cd contracts && forge install && forge test)  # 9 contract tests
```

SQLite is a laptop convenience. The append-only triggers on `document` and `access_event`
are Postgres-only, so that guarantee isn't in force against SQLite — see
`adapters/db.py`.

---

## Deploy

**The contract**, to Monad Testnet:

```bash
cd contracts
forge install
export PODARENA_RPC_URL=https://testnet-rpc.monad.xyz
export PODARENA_ANCHOR_PRIVATE_KEY=0x...        # funded at faucet.monad.xyz
forge script script/Deploy.s.sol:Deploy --rpc-url $PODARENA_RPC_URL --broadcast
```

**The app**, to Render: push the repo, then New → Blueprint pointed at `render.yaml`. It
provisions the web service, a Postgres, and a 1GB disk for evidence blobs, and wires
everything except the two chain secrets. Set `PODARENA_REGISTRY_ADDRESS` and
`PODARENA_ANCHOR_PRIVATE_KEY` in the dashboard afterwards and redeploy.

Set `PODARENA_S3_BUCKET` instead if you'd rather keep blobs in object storage than on a
disk.

Before this ever holds a real track record, turn off `PODARENA_DEMO_FIXTURES` — demo mode
adds the fake broker domain to the DKIM allow-list.

---

## How it's put together

```
contracts/   Foundry. TrackRecordRegistry: anchor, logAccess, head.
core/        Pure Python. No I/O, no clock, no network. Types, tier algebra,
             DKIM verification, extractors, metrics, Merkle, reconciliation.
adapters/    DNS, blobs, database, chain. Everything impure.
worker/      The seven-step ingest pipeline.
api/         FastAPI, and the disclosure fence.
verifier/    The standalone cold verifier.
web/         React + Vite + viem. Charts are hand-rolled SVG.
demo/        The synthetic corpus and the staged demo.
```

`core` depends on nothing. That's what makes the maths reproducible, and it's why
verification is a two-step dance: `required_dns_names()` says what to look up, an adapter
looks it up, and the pure verifier judges. The same function verifies a live message and a
ten-year-old archived one.

### Four decisions worth arguing about

**The tree commits to four things, not one.** Every document's hash, every DKIM verdict
*including the hash of the captured DNS key*, every fact, and the metrics result with the
methodology version and every extractor version. Bump a parser and the root moves. A root
over facts alone would let us silently change how we read a document and keep the same
story.

**Authenticity and interpretation are separate objects.** DKIM proves the bytes left the
institution. It says nothing about whether our parser read `NAV: 41,207,338.22` correctly.
So extractors are pure versioned functions, the version travels with every fact, and you
can always pull the original document and check our reading.

**Drawdown is measured on the return index, not on NAV.** A manager who returns capital to
investors has not lost money, and a drawdown built from raw NAV says he has. There's a
test where NAV falls 20% on a withdrawal and max drawdown is correctly zero.

**Money is `BIGINT` minor units; metrics compute in `Decimal` with explicit quantization.**
Not style. Float non-determinism across machines would produce different roots for the same
evidence, and the anchor would mean nothing. `core/canonical.py` refuses to serialize a
float at all. The one departure: a per-unit *price* is a Decimal rather than minor units,
because FX quotes past two decimals and squeezing `182.4750` into cents would destroy real
precision inside a hashed object — see the note in `core/types.py`.

### What we deliberately didn't build

**No agent-logs-in scraping.** It's in the tier model so imported data can be graded
honestly, but shipping it buys no stronger signature than Plaid and costs credential
custody plus most brokers' ToS. A liability dressed as a feature.

**No Redis or task queue.** A message takes milliseconds to verify and parse, and Monad
confirms in well under a second. The pipeline is a plain function, so putting it behind a
queue later is a change of caller, not a rewrite.

**No Alembic.** There's one deployment and no schema history to migrate. A half-used
migration tool implies a guarantee about upgrade paths that has never been exercised —
`adapters/bootstrap.py` is honest about what this is.

---

## Tests

99 Python tests and 9 Solidity tests. The ones that matter:

- **Determinism** — a golden Merkle root checked into the repo, so a different machine and
  a different day have to agree. Plus: leaf order doesn't move the root, one minor unit
  does, and bumping an extractor version does.
- **DKIM corpus** — all 18 fixtures against real RSA, with a test asserting the verifier
  never opens a socket.
- **Tamper drill** — flip a byte: the verdict fails, the tier drops, the root differs, and
  the record says so unprompted.
- **Seats** — a PM token opens its own pod and 404s on every route of the pod next
  door, and a token forged by swapping the slug fails the MAC.
- **Projection** — every disclosure profile asserted against the *serialized wire payload*,
  not the component. A field a profile forbids is never assembled, so there's no
  client-side toggle to defeat.
- **Cold verify** — the bundle proves itself with no access to the API.

Built from [`docs/build-plan.md`](./docs/build-plan.md).
