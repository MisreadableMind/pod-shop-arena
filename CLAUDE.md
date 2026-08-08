# pod-shop-arena

A Monad Blitz London hackathon project. Full ruleset, tooling list, and Monad
cheat-sheet: [`docs/blitz-rules.md`](./docs/blitz-rules.md) — that doc is the only copy
of the organisers' brief we keep.

## The clock

**Submission freezes at 5:45 PM**, at [blitz.devnads.com](https://blitz.devnads.com).
**Submission order sets pitching order.** Work backwards from 5:45 — deployment,
README, screenshots, and fallback recording all have to be done *before* that, not
after. If we're deciding between one more feature and submitting on time, submit.

## Eligibility gates — miss one and we don't get to pitch

1. Repo is a fork of `monad-blitz-london`. ✅ this repo already is.
2. `README.md` explains what it does, how to set it up, how to run it.
3. Contracts live on Monad Testnet (Mainnet also allowed; Testnet satisfies both
   sources — see the conflict note in the rules doc).
4. Contracts deployed **inside the event timeline** — deploy early and redeploy as we
   go, so there's never a moment where nothing is on-chain.
5. The app is **live on the web** at a public URL. Locally hosted = disqualified,
   explicitly.

Treat 2–5 as work items with real deadlines, not paperwork for the end of the day.
Gate 4 can't be fixed retroactively.

## Hard constraints — these override normal defaults

- **All code is written fresh, today.** Don't pull in an existing project, don't port
  code from another repo, don't scaffold from someone's finished app. Standard libraries
  and plain boilerplate (create-next-app, Foundry init, shadcn) are fine. Anything
  beyond that isn't. Forking the starter repo is required and doesn't count.
- **Deployed, not mocked.** Keep the live URL and deployed contract addresses in
  `README.md`.
- **Public repo.** No secrets, keys, or `.env` values in commits. Check before every
  commit.
- **Max 4 team members.**

## What "good" means here

Scoring is **50% judge votes, 50% participant votes**, on novelty, innovative mechanics,
problem-solving, and visible experimentation — explicitly *not* polish. So when there's
a trade-off, spend the time on the mechanic that makes people go "huh, that's new" and
let the rough edges be rough. A clone with a nicer UI scores near zero; a weird idea
that only works because of Monad scores well.

Four paid places (1200 / 800 / 500 / 500 USD), plus tracks and bounties listed in the
info pack — **we don't have the info pack yet, and it's the one input most likely to
change scope.** Get it before locking the idea.

Concretely, when I propose something:

- Prefer designs that only work on Monad. 0.3 s blocks, 0.6 s finality, 500M gas/sec —
  the pitch should be "this would be absurd on a slow chain." The brief's own list of
  what that unlocks: real-time fully on-chain apps, AI agents with on-chain state,
  high-frequency gaming and DeFi, Web2-feeling payment rails, heavy ZK.
- Don't gold-plate. No elaborate test suites, abstraction layers, or feature breadth
  unless load-bearing for the demo.
- Cut scope toward one impressive flow rather than five half-flows.
- Don't rebuild infra. Indexers, oracles, wallets, account abstraction, and agentic
  payment rails already exist on Monad — see the tooling section of the rules doc.
- For anything Monad-specific, read `docs.monad.xyz/llms-full.txt` or
  `docs.monad.xyz/developer-essentials` rather than guessing from memory.

## The demo is a deliverable

3 minutes, live, to a room of developers plus judges. Every build decision gets checked
against "can this be shown in 3 minutes without explanation?" Keep a demo-ready path
working at all times: if `main` can't be demoed, that's the top-priority bug.

Organisers' explicit tips, which shape how we build, not just how we present:

- **Stage the demo.** Pre-fill forms, pre-create an example. The audience should see the
  magic, not the typing. Build seed/demo-data scripts as we go.
- **Don't ship a default Tailwind blob.** This is the one place UI matters: pick a brand
  kit — typeface, colour, components — early and apply it consistently. Not polish for
  its own sake; just don't look unstyled. Then stop.
- **Fewer slides, more demo.** Problem stated in one breath, then straight to the build.

Before the pitch slot: stable deployment, screenshots of key flows, short fallback
recording.

## Working style

- Commit often, small readable commits — the repo is part of the submission and peers
  will read it.
- `README.md` is judged. It needs: one-line what-it-is, why it's novel, the live link,
  contract addresses, and local setup steps.
- Preferred stack, per the brief: **viem 2.40+** (native Monad testnet/mainnet support)
  and **Monad Foundry** (`curl -L https://foundry.category.xyz | bash`) for contracts.
