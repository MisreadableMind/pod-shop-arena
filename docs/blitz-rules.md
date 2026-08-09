# Monad Blitz London — Rules, Judging, Demo, Tooling

Everything binding for this project, merged from the official 60-slide hackathon brief
(not kept in this repo) and the organisers' written rules /
[Submission Process](https://monad-foundation.notion.site/Submission-Process-cc66367594f2837c898701aabd948402).
This file is now the only copy of the brief's contents we have.

**Where the two sources disagree, it's flagged inline.** Ask an organiser rather than
guessing.

---

## 0. The shape of the day

> "An innovation sprint. Not a marathon. A one-day burst of creativity to rapidly
> prototype new ideas on Monad. A safe space to try bold, unconventional things.
> Failure and learning are celebrated."

| Focus on | Worry less about |
| --- | --- |
| 💡 Novel mechanics & unique ideas | 🎨 Perfect UI / UX |
| 🧪 Exploring the limits of Monad | ✅ Extensive feature lists |
| ✨ Solving problems in new ways | 📊 Polished slide decks |

---

## 1. Hard deadlines & logistics

| Thing | Value |
| --- | --- |
| **Submission freeze** | **5:45 PM** |
| Portal (tokens, submission, voting) | [blitz.devnads.com](https://blitz.devnads.com) |
| Pitching order | **Determined by submission order** |
| Demo length | 3 minutes |
| Voting window | During presentations + **15 min after the final demo** |
| Wi-Fi | `Encode Club` / `Acce551969` |

**Submission order sets pitching order.** Submitting early buys a choice about where in
the running order you land, so decide deliberately rather than by accident.

---

## 2. Eligibility — five gates to qualify for pitching

Every project must clear all five:

1. **Fork the starter repo.** Build from a fork of `monad-blitz-london`.
2. **Ship a proper README.** Clear setup, what it does, and how to run it.
3. **Deploy on Monad.** Live on Monad **Testnet or Mainnet**.
4. **Deploy during the Blitz.** Contracts must be deployed within the event timeline.
5. **Live on the web.** A working, deployed app — not slides alone.

Miss any one and the project doesn't get to pitch, however good it is. Gate 4 is the
only one that can't be fixed retroactively.

> ⚠️ **Conflict:** the written rules say the project must be on **Monad Testnet**; the
> brief's eligibility slide allows **Testnet or Mainnet**. Testnet satisfies both, so
> default to Testnet.

---

## 3. Rules of engagement

**01 Start fresh.**
All project code must be written today. No existing personal projects. Standard
libraries are fine. The written rules add: you cannot submit existing projects, fork
existing codebases beyond standard libraries/boilerplates, or continue personal
projects already started. (Forking the `monad-blitz-london` starter is required and
doesn't count.)

**02 Ship live deployments.**
Every submission must be deployed with a working, accessible demo link. **Locally
hosted projects will be disqualified.**

**03 Public repositories.**
Code lives in a public GitHub repo for everyone to see and learn from.

**04 Be ready to demo in three minutes.**
Pitching order is determined by submission order. Slides are optional. The demo is the
point.

**Team size.** Maximum 4 members. *(From the written rules; the brief doesn't mention
it.)*

**Innovate, don't just replicate.** Direct clones of existing apps without significant
innovation or a Monad-specific twist are strongly discouraged. The question to answer:
"What new problem am I solving, or how am I solving an old problem in a radically new
way on Monad?"

**Planning ahead is encouraged.** Coding starts at the Blitz, but research,
brainstorming, and arriving with a concept are explicitly welcomed.

---

## 4. Demos & judging

Three minutes. The room decides.

**The demo**

- Show the live build. Lead with the live demo and the core innovation.
- Your audience is everyone in the room — fellow builders, not VCs or non-technical
  judges. Impress developers.
- Slides not required. Just present the demo.

**How votes work**

- Vote for the most innovative, technically interesting, or inspiring project.
- **Results are decided by a mix of judge and participant votes, weighted 50% each.**
- Teams cannot vote for their own project.
- After the 15-minute window closes, scores are tallied automatically and winners are
  announced.

> ⚠️ **Conflict:** one brief slide says "No official judges. The room decides," while
> the detail on the same slide says results are **50% judge / 50% participant**. The
> written rules describe it as purely community-driven. Treat it as 50/50 — that's the
> most specific claim, and it means a demo has to land with both a peer audience and a
> judge.

**Voting criteria**

- **Novelty & originality** — a truly new idea, a unique application of technology, or
  a fresh approach to an existing problem?
- **Innovative mechanics** — clever or novel mechanics, smart contract designs, or user
  interactions, especially ones that leverage Monad's potential?
- **Problem-solving** — does it creatively address a real or interesting challenge for
  consumer applications?
- **Learning & experimentation** — willingness to experiment, push boundaries, and
  learn, even if not every aspect is polished?

**The spirit of the vote.** Not the most polished or complete application — the new
idea, the unique approach, the thing everyone can learn from. Vote for what excited you
most with its ingenuity.

---

## 5. Presentation tips from the organisers

Filed under "BONUS · VERY, VERY IMPORTANT" in the brief.

**Tip 01 · Slides — fewer slides, more demo.**
Use slides to state the problem in one breath, then get to the live demo. The room came
to see your build, not your deck.

**Tip 02 · UI — don't ship vibe-coded UI.**
Give the LLM a brand kit: typeface, colour, components. *"A real design beats a default
Tailwind blob."*

> Note the tension with "worry less about perfect UI/UX." Read together: don't spend the
> day on polish, but don't hand the room an unstyled default either. One coherent brand
> kit applied consistently, then stop.

**Tip 03 · Demo flow — pre-fill your forms, stage your demo.**
The judge sees the magic, not the typing. Better yet: have an example pre-created.

**From the written rules, also:**

- Practise the timing — 3 minutes is short.
- Focus on the core innovation; don't show every feature.
- Prepare for demo gremlins: screenshots of key flows, a short fallback recording, and
  a stable deployment.
- Be clear on "what" and "why" fast, then get to the demo.

---

## 6. Prizes

Tracks, bounties, and overall prizes are in the info pack — check it **before** scoping
the build, since a bounty may be worth aiming at deliberately.

| Place | Prize |
| --- | --- |
| 🥇 1st | 1200 USD |
| 🥈 2nd | 800 USD |
| 🥉 3rd | 500 USD |
| 🥉 4th | 500 USD |

> 📌 **Missing:** we don't have the info pack itself, so the tracks and bounties are
> unknown. Get it — it's the one input most likely to change scope.

---

## 7. Monad cheat-sheet

Useful for the "how you built it" and "why this needs Monad" parts of the pitch.

**By the numbers**

| Property | Monad | Ethereum L1 |
| --- | --- | --- |
| Throughput | 500M gas / sec | 5M gas / sec |
| Block time | 0.3 s | 12 s |
| Finality | 0.6 s | ~13 min |
| Sustained TPS | 10,000 | ~28 |
| Active validators | 200 | ~27,000 / block |

**The six architecture primitives** (no contract changes required — existing Solidity
deploys unchanged):

*Execution*

- **Asynchronous execution** — consensus doesn't wait for execution; each gets a full
  block to work. (Restaurant where front of house never waits for the kitchen.)
- **Optimistic parallel execution** — run transactions at the same time; re-run only
  the few that clash. (A team editing one shared doc, each in their own section.)
- **MonadDB** — a database built for blockchain state, so reads stop being the
  bottleneck.

*Consensus & runtime*

- **MonadBFT** — validators agree in one round, so blocks are final in 600 ms.
- **RaptorCast** — blocks split into pieces and spread across the network in parallel.
- **JIT compilation** — contract bytecode compiles to native code once, then runs from
  cache.

**What 600 ms finality unlocks** (the brief's own list of what's new on Monad):

- Real-time, fully on-chain apps
- AI agents with on-chain state
- High-frequency gaming and DeFi
- Payment rails that feel like Web2
- Computationally heavy ZK and privacy

Same as Ethereum: Solidity and the same compiler, Foundry / Hardhat / viem / ethers,
the same EVM model (accounts, gas, tx ordering), the same JSON-RPC and WebSocket
surface.

---

## 8. Tooling — don't rebuild what's shipped

Full catalog: [docs.monad.xyz/tooling-and-infra](https://docs.monad.xyz/tooling-and-infra).

**Frameworks**

- **viem 2.40+** — native Monad testnet and mainnet support, same client patterns.
- **Monad Foundry** — a Foundry fork with Monad-native EVM execution, staking
  precompile support, human-readable trace decoding, and gas during simulation.
  Install: `curl -L https://foundry.category.xyz | bash`

**Categories and named options** (logos in the deck; names below are the ones legible —
check the catalog for the rest)

- **Indexers** — Envio, Goldsky, Allium, Moralis
- **Oracles, wallets, RPC** — Chainlink, Pyth, Alchemy, QuickNode, MetaMask
- **Account abstraction** — Privy, Para, Mera (marked *free*)
- **Bridges & swaps** — see catalog

**Agentic payments & agent identity**

- **x402 on Monad** — free facilitator hosted by Monad.
  [docs.monad.xyz/guides/x402-guide](https://docs.monad.xyz/guides/x402-guide)
- **MPP on Monad** — `@monad-crypto/mpp`
- **ERC-8004 on Monad** — on-chain identity for AI agents

**Mobile** — React Native and PWA templates for native mobile apps on Monad.

**AI-assisted building**

- [skills.devnads.com](https://skills.devnads.com) — coding-assistant skills to build
  Monad apps in a few prompts: built-in testnet faucet, contract dev & deploy, frontend
  dev & deploy, indexer deployment.
- [app.monad.xyz/agents](https://app.monad.xyz/agents) — agent-readable skills from
  ecosystem projects; point an agent at a protocol and let it quote, build, and prepare
  transactions. DeFi: Uniswap, Morpho, Balancer, Kuru, Clober. Launchpads & tokens:
  Nad.fun. Gaming & prediction: DevFun, Blinq.fi.

> Disclaimer carried from the deck: these skills are maintained by ecosystem projects
> and are **not audited** by Monad Foundation.

**Docs**

- [docs.monad.xyz/developer-essentials](https://docs.monad.xyz/developer-essentials) —
  almost everything needed to build.
- `docs.monad.xyz/llms-full.txt` — comprehensive single-file source for AI coding
  assistants. **Feed this to the agent instead of guessing at Monad specifics.**
- [developers.monad.xyz](https://developers.monad.xyz) — docs, events, Discord.
- [github.com/monad-developers](https://github.com/monad-developers) — examples,
  starter kits, toolchain changes.
- [gmonads.com](https://gmonads.com) — live validator / block-time view (good B-roll for
  a demo).

---

## 9. Submission process

1. Fork [`monad-developers/monad-blitz-london`](https://github.com/monad-developers/monad-blitz-london).
2. Give the fork your project name and a one-liner description, fork the `main` branch,
   click **Create Fork**.
3. In your fork, change anything and everything — add project code, create branches,
   fill in `README.md`.
4. Submit at [blitz.devnads.com](https://blitz.devnads.com) — also where you claim
   tokens and vote. **Freeze at 5:45 PM.**

This repo (`pod-shop-arena`) is that fork.

---

## 10. After the Blitz

- **MOST** (Monad Open Source Track) — contribute to open source, earn AI credits.
- **AI Blueprint** — resources, infra, and support to build and scale AI apps on Monad.
- **Delta V** — members-only community for founders building on Monad.
- **BuildAnything.so** — go from vibe coder to production-ready apps.
