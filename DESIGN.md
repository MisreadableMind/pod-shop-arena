# Pod Arena — Design Practices

A living record of the conventions actually in force across this repo — product,
architecture, backend, frontend, and the **"New Genre"** visual system. Everything
below is distilled from the code as it stands, not aspiration; file references point
at the canonical example of each practice. When you add code, match what's here.

Related docs: [README](README.md) · [REQUIREMENTS](REQUIREMENTS.md) ·
[docs/ARCHITECTURE](docs/ARCHITECTURE.md) · [docs/IMPLEMENTATION](docs/IMPLEMENTATION.md) ·
[docs/SECURITY](docs/SECURITY.md) · [docs/COMPLIANCE](docs/COMPLIANCE.md).

---

## 1. Product design principles (non-negotiable)

These are the product's spine (REQUIREMENTS.md §2). They are not slogans — each is
enforced by a specific piece of code. Changing the code without honoring the principle
is a regression.

| Principle | How it's enforced in code |
|---|---|
| **Source of truth only** — no hand-typed metrics, ever | `computeMetrics()` reads *only* a normalized snapshot series (`packages/core/src/metrics/engine.ts`); manual entity fields (bio, strategy) are surfaced but explicitly labeled `unverified` in the UI (`apps/web/src/routes/RecordPage.tsx`). |
| **No made-up metrics** — same inputs → same numbers | One pinned `METHODOLOGY_VERSION` (`metrics/engine.ts`); the engine is pure and the wall-clock is **injected** (`now` param), never read inside the computation. The determinism contract is unit-tested (`packages/core/src/core.test.ts`). |
| **Exclusivity fence** — nothing public, least-privilege | Disclosure filtering happens **server-side** so hidden data never crosses the wire (`apps/api/src/services/disclosure.ts`); invites gate on revoke/expiry/NDA (`apps/api/src/routes/shared.ts`). |
| **Read-only, never custody** | The `Connector` interface exposes a single verb — `pull()`. No trade/withdraw surface exists to call (`packages/core/src/connectors/types.ts`). |
| **Verifiable, not asserted** | Viewers re-fold the Merkle inclusion proof **in their own browser** via WebCrypto and trust local math, not the server's boolean (`apps/web/src/api/client.ts::verifyProofInBrowser`, `components/VerificationPanel.tsx`). |
| **Privacy-preserving proof** | Absolute $ figures and positions are stripped unless the viewer's profile grants them; `zk_proven` is modeled as a first-class badge tier (`packages/core/src/types.ts`). |

**Rule of thumb:** every number shown to a user must trace back to a hashed snapshot,
carry its methodology version, and be labeled with a trust tier. If you can't show
where a value came from, it doesn't ship.

---

## 2. Repository & module architecture

**Monorepo, three layers, one direction of dependency.**

```
packages/core   ── the domain heart. Framework-free, pure, unit-tested.
      ▲                Depends on nothing but Node builtins.
      │ (workspace:*)
apps/api        ── Fastify BFF. Persistence + orchestration + the fence.
      ▲                Depends on core. Never imported by core.
      │ (HTTP/JSON)
apps/web        ── Vite + React SPA. Depends on api only over the wire.
```

- **pnpm workspaces** (`pnpm-workspace.yaml`): `packages/*` + `apps/*`, packages named
  `@pod-arena/{core,api,web}`, internal deps pinned `workspace:*`.
- **`packages/core` is the source of truth for domain logic and types.** If a rule is
  about *what a metric means* or *what shape the data has*, it lives here — not in the
  API and not in the web app. The API and web app both re-declare matching TS shapes
  and stay in sync by convention (`apps/web/src/api/client.ts` mirrors `core/src/types.ts`).
- **ESM everywhere.** Every package is `"type": "module"`; TS source imports use explicit
  `.js` extensions (`import { x } from './foo.js'`) even for `.ts` files.
- **No build step for `core`/`api`.** They run directly through `tsx`
  (`node --import tsx …`); only `web` builds (Vite). `core` is consumed straight from
  `./src/index.ts` (see its `package.json` `main`/`exports`).
- **Shared TS baseline** (`tsconfig.base.json`): `strict`, **`noUncheckedIndexedAccess`**,
  `noImplicitOverride`, `moduleResolution: Bundler`, target/lib ES2022. The strict
  index-access setting is why you'll see `arr[i]!` and `?? fallback` throughout — honor it
  rather than loosening the config.

---

## 3. Domain layer conventions (`packages/core`)

- **Types-first.** Canonical domain types live in `src/types.ts` with heavy doc-comments
  explaining *why* each field exists and its invariants (ISO date formats, sign
  conventions, "ascending by date", "never mutated"). Read those comments before adding
  a field.
- **Barrel export.** `src/index.ts` re-exports every public submodule; consumers import
  from `@pod-arena/core`, never deep paths.
- **Pure & deterministic.** Functions take data in, return data out. No wall-clock, no
  randomness, no I/O inside computation. Where "now" is genuinely needed it's a parameter
  (`MetricsInput.now`). This is what makes results reproducible and testable.
- **Provenance travels with the value.** Every `MetricValue` carries `formula` + `inputs`
  strings (`metrics/engine.ts`) so the UI's methodology drawer can show how each number
  was produced. New metrics must include both.
- **Methodology versioning.** `METHODOLOGY_VERSION` is pinned to every result. **Bump it on
  any change to a formula or convention** — the comment on the constant says so.
- **Small, single-purpose modules.** Math is split by concern: `metrics/returns.ts`,
  `metrics/risk.ts`, `metrics/ratios.ts`; verification into `hash.ts` + `merkle.ts`.
- **Interface + registry for pluggability.** `Connector` is an interface; real connectors
  (Plaid, IBKR, SFTP) "drop in behind the same contract; the pipeline never knows the
  difference" (`connectors/types.ts`). The mock is deterministic (seeded).
- **Compliance blocks, it doesn't flag.** `evaluateMarketingRule()` returns
  `compliant: false` + `violations[]` when a presentation is non-conforming; a
  non-compliant presentation is **blocked from display/export**, not merely warned
  (`compliance/disclaimers.ts`).

---

## 4. Backend conventions (`apps/api`)

- **Fastify BFF; routes are plugins.** Each route module exports an
  `xRoutes(app: FastifyInstance)` function registered in `src/server.ts`
  (`authRoutes`, `recordRoutes`, `verifyRoutes`, `sharedRoutes`).
- **Config in one place.** All env reads go through `src/env.ts` using the
  `process.env.X ?? default` pattern; no `process.env` access scattered elsewhere.
- **Repository pattern over `node:sqlite`.** `src/db/repo.ts` is the only module that
  touches the DB. Conventions there:
  - A typed `interface` per table row (snake_case columns, mirroring SQL).
  - Prepared statements inline; `nowIso()` helper for timestamps.
  - **Prefixed UUID ids** by entity type: `ent_`, `usr_`, `con_`, `rec_`, `mst_`,
    `anc_`, `inv_`, `aud_`. Keep the prefix scheme when adding tables.
  - Emails stored/queried lower-cased.
- **Immutable, content-addressed vault.** Raw pulls are written to `<sha256>.json`
  write-once (`flag: 'wx'`), re-storing identical data is a no-op, and reads re-verify
  the content hash against the filename — a mismatch throws a "vault integrity violation"
  (`src/vault/index.ts`). The vault is never mutated post-write.
- **Auth is swappable.** Stateless HMAC-signed bearer tokens + scrypt password hashing
  (`src/auth/index.ts`); a `preHandler` hook decorates `req.user` (null when absent).
  The comment states the intent: swap for WebAuthn/MFA later, **the middleware surface
  stays the same**. Preserve that seam.
- **Centralized error handling.** `app.setErrorHandler` maps `ZodError → 400
  {error:'validation_error', issues}` and otherwise honors `err.statusCode`. Input is
  validated with **Zod** at the route boundary.
- **Typed result unions for gating.** The fence uses a discriminated `Gate` union
  (`{ok:true, invite} | {ok:false, code, error}`) instead of throwing for expected
  denials (`routes/shared.ts`). Prefer this for expected, user-facing rejections.
- **Audit logging is a first-class side effect.** Every meaningful action calls
  `appendAudit({ actor, action, target, meta, ip })` — landing, NDA accept, view, sync,
  verify. Actions are dotted namespaces (`shared.view`, `record.sync`). New sensitive
  actions must be audited.
- **The core loop is one orchestrator.** `services/ingestion.ts::syncRecord()` runs the
  whole pipeline in numbered steps: pull → store snapshot → normalize → compute metrics →
  anchor → audit. Read it as the reference for how the pieces compose.

---

## 5. Frontend conventions (`apps/web`)

- **Stack:** Vite + React 18 + **TanStack Router / Query / Table**. Routes are defined
  declaratively in `src/router.tsx` and registered on the root route.
- **One typed API client.** `src/api/client.ts` owns *all* network access: a single
  generic `req<T>()` wrapper (sets JSON + bearer header, throws typed `ApiError`), an
  `api` object of endpoint functions, and response interfaces that mirror the backend.
  Components never call `fetch` directly.
- **Server state via TanStack Query.** `useQuery` with array `queryKey`s
  (`['record', id]`, `['audit', id]`), `enabled: !!user` to defer until authed, and
  `useMutation` + `queryClient.invalidateQueries` for writes (`routes/RecordPage.tsx`).
- **Auth context + redirect guard.** `useAuth()` provides `{user, loading, logout}`;
  protected pages redirect via `useEffect(() => { if (!loading && !user) navigate(...) })`.
- **Explicit loading / error / empty states as early returns** before the happy path
  (see the guard ladder at the top of `RecordPage`).
- **Presentational components take typed props;** shared formatting lives in
  `components/format.ts` (`formatMetric`, `metricTone`, `shortHash`, `timeAgo`) — keep
  display logic there, not inline.
- **No chart dependency.** Charts are hand-rolled inline SVG (`components/EquityCurve.tsx`)
  so "the picture and the numbers can never disagree" — the curve is the same linked-TWR
  series the engine produced. Reach for SVG before adding a charting library.
- **Independent verification client-side.** The viewer recomputes the Merkle root with
  WebCrypto (`verifyProofInBrowser`) rather than trusting the server's answer.

---

## 6. Visual design system — "New Genre"

The full system lives in `apps/web/src/styles.css`. It is deliberately opinionated;
its header comment is the manifesto. Core rules:

### Tokens
- **Everything is a CSS custom property** declared in `:root`. Semantic aliases
  (`--surface-card`, `--hairline`, `--text-dim`, `--radius-card`, …) sit on top of raw
  named colors (`--color-onyx`, `--color-slate-veil`, …). A **legacy-compatibility layer**
  remaps older variable names (`--bg`, `--accent`, `--good`) onto the New Genre palette so
  inline styles stay coherent — extend tokens, don't hardcode hexes in components.

### Color
- **Achromatic UI.** The interface is near-white surfaces + blue-black Onyx text/controls.
  Chroma is spent almost nowhere.
- **The dawn-arc gradient IS the brand** — the single hero gradient
  (`--gradient-dawn-arc`, charred-umber → steel-blue → cream). It draws the hero banner,
  the brand mark, the verification accent band, and even the equity curve stroke.
  Emotion is carried by **gradient + type**, not by colorful UI.
- **Gain/loss is read from sign, not color.** `metricTone()` exists but the `.pos`/`.neg`
  classes resolve to the *same* Onyx — the numeral's `+`/`−` does the work. Don't
  introduce red/green semantics.

### Typography
- **Three families, clear jobs:** `--font-display` **Fraunces** (editorial condensed
  serif) is the brand voice at volume — hero, page titles, footer; `--font-sans`
  **Hanken Grotesk** carries all UI; `--font-mono` for hashes, formulas, and pills.
- **Numbers use `font-variant-numeric: tabular-nums`** everywhere they're compared
  (metric tiles, tables, method rows).
- Tight tracking (`letter-spacing: -0.01em`/`-0.02em`), low weights (400–500), optical
  sizing on display type. `clamp()` for fluid title sizing.

### Form & elevation
- **Elevation via lightness, never drop shadows.** Cards are a lighter/inset surface with
  a **hairline** border (`--hairline`/`--hairline-soft`), not `box-shadow`.
- **Shape language:** 16px card radius (`--radius-card`); **pills** for controls, inputs,
  and badges (`--radius-pill: 50px`).
- **Motion is minimal:** 0.15s ease transitions on interactive states; a single `spin`
  keyframe. No large animations.

### Component patterns (class vocabulary)
- **Cards:** `.card` + `.card-head` (title left, quiet meta/`.pill` right).
- **Badges encode the trust hierarchy visually:** `.badge-live` = solid fill (highest
  trust), `.badge-zk` = outline, `.badge-unverified` = quiet/greyed. `Badge.tsx` maps
  every `BadgeTier` to text + class + an explanatory `title` tooltip.
- **Metric tiles** (`.metric-tile`), **hashlines** (`.hashline` k/v rows for
  cryptographic values), **method rows** (label + big value + formula + inputs),
  **watermark layer** (fixed, low-opacity, rotated, per-viewer identity),
  **dawn-arc accent band** on the verification card.
- **Layout:** sticky frosted-glass header (`backdrop-filter: blur`), full-bleed hero
  gradient, `max-width: 1400px` centered container, `.grid-2` (1.6fr/1fr) that collapses
  to one column at `max-width: 900px`, dark footer that bookends the dawn arc.

### Voice
Copy is part of the trust design: *"Proof over PDFs"*, *"Proof, not promises."*,
*"Claims fade. Proof lasts."* Keep product copy terse, confident, and about verifiability.

---

## 7. Trust & verification design (the moat)

- **Trust is layered and always labeled**, strongest → weakest, encoded as `BadgeTier`
  with an explicit `BADGE_RANK` (`packages/core/src/types.ts`): `live_connected` >
  `zk_proven` > `third_party_attested` > `document_ingested` > `unverified`. Every metric
  surfaced to a viewer carries the tier of the data it came from.
- **Notarization mechanics:** snapshot content-hash → Merkle tree → root → (simulated)
  on-chain anchor. Only the root is "published"; raw data never leaves the vault.
  Tree hashing is domain-separated SHA-256 over child hex, Bitcoin-style odd-node
  duplication (`verification/merkle.ts`).
- **Provenance is surfaced in the UI**, not hidden: the source-attestation strip
  (institution · access method · last sync · period · methodology version pill) and the
  on-chain verification panel are always present on a record page.
- **Manual context is quarantined.** Anything a human typed (strategy, bio) is rendered
  with an `unverified` badge next to it.

---

## 8. Testing & quality gates

- **Determinism is the contract that gets tested.** `packages/core/src/core.test.ts` runs
  via `node --import tsx --test` and asserts same inputs → same hash → same metrics →
  same Merkle root, plus tamper-detection and compliance behavior.
- **Typecheck is the broad gate:** `pnpm typecheck` runs `tsc --noEmit` across every
  workspace (`pnpm -r`). Keep the tree green under the strict config.
- **Test the domain, not the framework.** Unit tests target `packages/core` (the pure
  layer); the API/web layers are thin orchestration/presentation over it.

---

## 9. Deliberate stubs — where practice bends for the spike

The current tree is an honest vertical slice (see [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)).
Some things are consciously stubbed **behind stable interfaces** so the real
implementation drops in without touching callers:

- Only the deterministic mock Plaid connector (real ones implement the same `Connector`).
- On-chain anchoring is simulated (`base-sepolia (simulated)`); the Merkle math is real.
- ZK proofs are modeled as a badge tier; no circuit yet.
- Identity (KYC/KYB, passkeys/MFA/step-up) and encryption-at-rest are not built; the
  auth middleware surface and SQLite schema already mirror the production shape.

**The discipline that matters:** when you replace a stub, keep the interface. The mock and
the real thing must be swappable without the pipeline noticing.

---

## Conventions cheat-sheet

| Area | Convention |
|---|---|
| Language / modules | TypeScript, ESM, `"type":"module"`, `.js` import extensions |
| TS strictness | `strict` + `noUncheckedIndexedAccess` + `noImplicitOverride` (expect `!` / `?? x`) |
| Runtime | `tsx` for `core`/`api` (no build); Vite for `web` |
| Dependency direction | `web → api (HTTP) → core`; `core` depends on nothing |
| Domain types | Defined once in `core/src/types.ts`, mirrored in the web client |
| Determinism | No clock/randomness/I/O in `core`; inject `now`; bump `METHODOLOGY_VERSION` on formula changes |
| DB ids | Prefixed UUIDs: `ent_ usr_ con_ rec_ mst_ anc_ inv_ aud_` |
| DB access | Only through `apps/api/src/db/repo.ts` (repository pattern) |
| Vault | Content-addressed `<sha256>.json`, write-once, integrity re-checked on read |
| Validation | Zod at route boundaries; central `setErrorHandler` |
| Expected denials | Discriminated result unions (`Gate`), not thrown errors |
| Auditing | `appendAudit()` on every sensitive action; dotted `namespace.action` names |
| Frontend data | TanStack Query, array `queryKey`s, one typed `api` client, no raw `fetch` |
| Charts | Hand-rolled inline SVG, no chart library |
| Color | Achromatic UI; dawn-arc gradient is the only brand color; gain/loss via sign |
| Type | Fraunces (display) / Hanken Grotesk (UI) / mono (hashes); tabular-nums for numbers |
| Elevation | Lightness + hairline borders, never shadows |
| Tokens | CSS custom properties in `:root`; extend tokens, don't hardcode |
| Trust | Every value carries a `BadgeTier`; manual input labeled `unverified` |
```
