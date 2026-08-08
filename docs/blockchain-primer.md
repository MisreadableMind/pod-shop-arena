# Blockchain, smart contracts, and Monad — a working primer

Notes for building `pod-shop-arena` at Monad Blitz London. Facts checked against
[docs.monad.xyz](https://docs.monad.xyz/) in August 2026. Anything I'm inferring rather
than quoting is marked *(my read)*.

---

## 1. What a blockchain actually is

Forget tokens for a second. A blockchain is **one computer that thousands of machines
run in lockstep so that nobody has to trust the operator.**

That's it. Every node executes the same programs on the same inputs in the same order,
gets the same answer, and keeps the same memory. If one node lies, the others notice.

Three things follow, and they explain nearly every weird constraint you'll hit:

1. **It's slow and expensive per unit of compute.** You're paying thousands of machines
   to redo the same work. A loop that costs nothing on a server costs real money here.
2. **It's deterministic.** Every node must reach an identical result. So: no random
   numbers, no `fetch()`, no reading a file, no `Date.now()`. Any of those would make
   nodes disagree.
3. **It's public.** Every node has the state, so everyone has the state. There are no
   secrets, only unread data.

What you get in exchange is the interesting part: **state that no single party can
change or roll back**, and **assets that move without an intermediary**. If your app
doesn't need either of those, a Postgres database is a strictly better choice and you
should say so out loud.

The clean way to think about it: a blockchain is a *very slow, very expensive,
publicly-auditable computer with a built-in bank account.* You put the small,
trust-critical part of your app there — ownership, money, rules, the referee — and
everything else stays on a normal server.

---

## 2. What a smart contract is

A smart contract is **a program deployed to an address, with its own permanent
memory, that only runs when someone sends it a transaction.**

Concretely:

- You write Solidity, compile it to EVM bytecode, and send that bytecode in a
  transaction. The chain assigns it an address like `0x5FbDB…`. That's deployment.
- The contract has **storage** — a key-value map of 32-byte slots that persists
  forever. Solidity dresses it up as `uint256 public score;` but underneath it's slots.
- It has **public functions**. Anyone can call them by sending a transaction to the
  address. The contract sees `msg.sender` (who called), `msg.value` (how much native
  currency they attached), and the arguments.
- **It cannot act on its own.** No cron, no background thread, no "when X happens, do
  Y." Nothing happens until an outside transaction pokes it. If you want something to
  happen every minute, someone off-chain has to send a transaction every minute.

Here's a whole contract. Read it once, then I'll pull it apart:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract Arena {
    // ---- storage: lives forever, costs money to change ----
    mapping(address => uint256) public wins;
    address public champion;
    uint256 public pot;

    // ---- events: cheap write-only log, for your UI to read ----
    event Challenged(address indexed challenger, bool won, uint256 pot);

    // ---- errors: cheaper than revert strings ----
    error StakeTooSmall();

    function challenge() external payable {
        if (msg.value < 0.01 ether) revert StakeTooSmall();

        // NOT random. Anyone can predict this. See §5.
        bool won = uint256(blockhash(block.number - 1)) % 2 == 0;

        if (won) {
            wins[msg.sender] += 1;
            champion = msg.sender;
            uint256 payout = pot + msg.value;
            pot = 0;
            // effects first, then the external call — see §5, reentrancy
            (bool ok, ) = msg.sender.call{value: payout}("");
            require(ok, "payout failed");
        } else {
            pot += msg.value;
        }

        emit Challenged(msg.sender, won, pot);
    }
}
```

Four things to notice, because they're the four things that make contracts different
from normal code:

**`payable` and `msg.value`.** The contract holds money natively. `msg.value` is MON
the caller attached to the call; the contract's balance goes up automatically. There is
no payment provider, no webhook, no reconciliation. Money movement and program logic
are the same operation. This is genuinely the superpower — everything else is a
constraint.

**`mapping`, and why it's a mapping.** Solidity has arrays, but you'll notice I used a
mapping. Iterating an array on-chain costs gas per element, and if the array can grow
without bound your function eventually costs more gas than a block allows and becomes
permanently uncallable. That's a real, common, unrecoverable bug. **Rule: never loop
over something a user can grow.** Mappings are O(1) lookups and can't be iterated —
that's a feature.

**`event` / `emit`.** Events are the write-only log. They cost roughly 375 gas plus
375 per indexed topic plus 8 per byte — far cheaper than storage — and contracts
*cannot read them back*. They exist purely for the outside world. Your frontend
subscribes to `Challenged` and updates the UI. Anything your UI needs to display but
your contract logic never needs to read should be an event, not storage. This is the
single biggest gas lever available to a beginner.

**`public` doesn't mean what you think.** `mapping(...) public wins` generates a getter,
sure. But `private` on a state variable only stops *other contracts* from reading it.
Every node has the raw storage. Anyone can `eth_getStorageAt` your "private" field and
read it. **There are no secrets in a contract.** Not passwords, not the answer to the
quiz, not the shuffled deck. If you need a hidden value, you need commit-reveal (hash
it now, reveal it later) or you keep it off-chain entirely.

---

## 3. The anatomy of a dapp

A blockchain app is five pieces. Beginners usually think it's two.

```
  ┌──────────┐   sign    ┌────────┐   raw tx   ┌─────────┐
  │ Frontend │──────────►│ Wallet │───────────►│ RPC node│
  │ (React)  │◄──────────│(MetaMask)          └────┬────┘
  └────┬─────┘  reads    └────────┘                │
       │                                            ▼
       │  events / queries                    ┌───────────┐
       └──────────────────────────────────────│  Chain    │
                    ┌─────────┐               │ (contract)│
                    │ Indexer │◄──────────────└───────────┘
                    └─────────┘   logs
```

- **The contract** — your rules and your state. Small. Should be boring.
- **The RPC node** — your database connection, basically. An HTTP endpoint that speaks
  `eth_call`, `eth_sendRawTransaction`, `eth_getLogs`. You don't run one; you use
  `https://testnet-rpc.monad.xyz`.
- **The wallet** — holds the user's private key and signs transactions. Your frontend
  *never* touches a key. It builds a transaction, asks the wallet to sign, the wallet
  broadcasts. That's the whole auth model: a signature from an address is the login.
- **The frontend** — normal React. `viem` + `wagmi` are the current default libraries.
  Two kinds of calls, and confusing them is the #1 beginner mistake:
  - **read** (`eth_call`) — free, instant, no wallet popup, changes nothing.
  - **write** (`eth_sendRawTransaction`) — costs gas, wallet popup, takes a block,
    can fail.
- **The indexer** — optional but usually necessary. Reading history straight from an
  RPC is slow and range-limited (see §6). An indexer subscribes to your events, writes
  them into Postgres, and gives your UI a normal API. For a one-day hackathon you can
  usually skip it and just subscribe to live events over a websocket.

**A transaction's life:** you sign it → it goes to a node → it reaches a block
producer ("leader") → it gets ordered into a block → the block is executed → a
receipt exists → the block gets finalized. Between "signed" and "receipt" your UI is
in a pending state and must handle it. On Ethereum that's ~12 seconds and you show a
spinner. On Monad it's under a second, which changes what you can design (§7).

---

## 4. The build loop, concretely

Monad runs EVM bytecode, so the standard Ethereum toolchain works unchanged — you
just point it at a different RPC. Foundry is the fast one; use it.

```bash
# once
curl -L https://foundry.paradigm.xyz | bash && foundryup

# new project
forge init arena && cd arena

# fast local loop — a full chain on localhost, instant blocks, 10 funded accounts
anvil

# tests are Solidity, and they're fast (milliseconds)
forge test -vvv

# deploy to Monad Testnet
forge create src/Arena.sol:Arena \
  --rpc-url https://testnet-rpc.monad.xyz \
  --private-key $PRIVATE_KEY \
  --broadcast

# verify so people can read your source on the explorer
forge verify-contract <ADDRESS> src/Arena.sol:Arena \
  --chain 10143 \
  --verifier sourcify \
  --verifier-url https://sourcify-api-monad.blockvision.org
```

Network details:

| | Testnet | Mainnet |
|---|---|---|
| Chain ID | `10143` | `143` |
| RPC | `https://testnet-rpc.monad.xyz` | `https://rpc.monad.xyz` |
| Explorer | `https://testnet.monadexplorer.com` | `https://monadscan.com`, `https://monadvision.com` |
| Gas token | MON (free from `https://faucet.monad.xyz`) | MON (real) |

Workflow that actually works under time pressure: **write the contract, test against
`anvil` until the logic is right, deploy to testnet once, then build the UI against the
deployed address.** Don't build the UI first. Redeploying is cheap; rewiring a UI
around a changed ABI is not.

There's a Monad-configured Foundry template at
[`monad-developers/foundry-monad`](https://github.com/monad-developers/foundry-monad) —
boilerplate, so it's within the Blitz rules.

---

## 5. The constraints — the honest list

This is the section that matters. Every one of these has cost somebody real money.

**Gas, and what's actually expensive.** Every operation has a price. The prices are
wildly non-uniform, and the ratio is the thing to internalize:

| Operation | Gas |
|---|---|
| Base cost of any transaction | 21,000 |
| Arithmetic (`ADD`, `MUL`) | 3–5 |
| Read a storage slot (first time in tx) | 2,100 |
| Read a storage slot (again) | 100 |
| **Write a fresh storage slot (0 → non-zero)** | **20,000** |
| Write an existing slot | ~2,900 |
| Emit an event | ~375 + 8/byte |
| Deploy code | 200 per byte |

Storage writes dominate everything. A thousand additions cost less than one fresh
storage write. So the optimization instinct is always the same: **fewer slots touched,
pack related values into one 32-byte slot, and push anything display-only into
events.** Monad keeps Ethereum's nominal opcode prices with a handful of items
repriced.

**Code is immutable.** Once deployed, the bytecode at that address never changes.
There is no `git push` to production. You fix a bug by deploying a new contract and
migrating — or by having built a proxy pattern up front, which splits your app into a
storage contract and a swappable logic contract and brings its own class of bugs. For
a hackathon: just redeploy. For anything holding real money: this is why audits exist.

**Reentrancy.** When your contract calls out to an address, that address might be a
contract, and it can call *back into you before your first call returns* — while your
state is half-updated. The 2016 DAO hack was this, for $60M. The fix is a discipline,
not a library: **checks, then effects, then interactions.** Validate, update all your
state, and only then make the external call. In the `Arena` example above, `pot = 0`
happens *before* `.call{value:}`. If you swap those two lines the contract can be
drained.

**Randomness doesn't exist.** `block.timestamp`, `blockhash`, `block.prevrandao` — all
visible or influenceable by the block producer, and all knowable by anyone simulating
your transaction before sending it. The `won` line in my example is exploitable on
purpose: a bot simulates the call, and only sends the transaction when it wins. For
real randomness you need a VRF oracle (Chainlink, Pyth Entropy) or commit-reveal.
*(For a hackathon toy, "provably unfair randomness" is fine if you say so on stage.)*

**No outside world.** A contract can't call an API, read a price, check the weather, or
know the time beyond `block.timestamp` (which is the producer's clock, ±seconds, and
nudgeable). Anything external must be *pushed in* by an oracle — someone off-chain
sending a transaction containing the data. Every "smart contract that reacts to
real-world events" is really a contract plus a bot.

**Everything is public and racing.** Your transaction is visible before it's mined, and
bots read it and can act on it. Someone sees your profitable trade and submits the same
one with a higher fee (front-running). Someone sandwiches your swap. This is MEV, and
it's not a bug you can patch — it's a property of shared block space. Monad softens
one part of this: **there is no global mempool**; transactions are forwarded to the
next few leaders rather than gossiped to everyone. Less exposure than Ethereum, but
never assume a pending transaction is private.

**Failure is loud and permanent.** A `revert` undoes all state changes in the
transaction — nice — but the gas is gone. And on Monad, *the whole gas limit* is gone
(§6). Money sent to a wrong address is gone. There is no support desk.

**Size and shape limits.** Ethereum caps deployed contracts at 24 KB, which forces
awkward splitting. Monad raises this a lot (128 KB, §6), so this is one constraint you
mostly don't have here.

---

## 6. What Monad changes — the numbers

Monad is **EVM bytecode-equivalent**: your Solidity, Foundry, viem, wagmi, MetaMask, and
OpenZeppelin all work with no changes. What differs is performance and a short list of
sharp edges you must know.

### Performance

Mainnet launched 24 November 2025. Official figures: **10,000 TPS, 300 ms blocks,
600 ms finality.** *(Some earlier material says 400 ms / 800 ms — the docs now say
300/600.)* Four pieces get it there:

- **MonadBFT** — pipelined consensus, resistant to tail-forking.
- **RaptorCast** — erasure-coded block propagation, so the leader doesn't have to send
  the whole block to everyone.
- **Asynchronous execution** — consensus agrees on the *order* of transactions before
  executing them. Ordering and execution run as a pipeline instead of a queue, which
  gives execution a much bigger time budget. This is the source of most of the sharp
  edges below.
- **Parallel execution** — independent transactions run at the same time, optimistically,
  with conflicts detected and re-executed. Plus JIT compilation of bytecode and
  **MonadDb**, a state database built for this access pattern instead of bolted onto
  LevelDB.

*(My read: because parallelism is optimistic, a design where every transaction writes
the same storage slot — one global counter, one shared leaderboard total — serializes
and re-executes. If you want to actually exercise Monad's throughput, shard your state:
per-user slots, per-item slots. That's a design choice worth making deliberately, and
worth mentioning on stage.)*

### The gas trap — read this one twice

**Monad charges you the gas limit, not the gas used.**

```
deducted = value + gas_bid × gas_limit
```

On Ethereum, setting a 1,000,000 limit and using 100,000 costs you 100,000. On Monad it
costs you 1,000,000 — 10× more. The reason is structural: leaders build blocks *before*
executing them, so a transaction's block space has to be paid for at reservation time,
otherwise you could squat 30M gas of block space for pennies.

The practical consequence: **set explicit gas limits on transactions with known costs.**
Wallets are known to slam the limit to something huge when a call reverts during
estimation, and on Monad that estimate is what you pay. If your UI does `writeContract`
without a `gas` field, you're at the wallet's mercy.

Other fee parameters:

| | |
|---|---|
| Minimum base fee | 100 MON-gwei (10⁻⁷ MON per gas) |
| Block gas limit | 200,000,000 |
| Target block gas | 160,000,000 (80%) |
| Per-transaction gas limit | 30,000,000 |
| Base fee adjustment | EIP-1559-like; slower increases, faster decreases |

So a 100k-gas call at the floor price is 0.01 MON. Set the limit to 1M "to be safe" and
you just paid 0.1 MON for nothing.

### VM differences

- **Contract code limit 128 KB** (Ethereum: 24 KB). Init code 256 KB (Ethereum: 48 KB).
  You can write a fat contract without diamond patterns.
- **Memory is priced linearly**, not quadratically, up to **8 MB per transaction**.
  On Ethereum, big in-memory arrays get quadratically punished; here they don't.
  *(My read: this makes heavy in-memory computation — simulation steps, pathfinding,
  matrix work — actually viable on-chain. That's an unusual and demoable capability.)*
- **P256 precompile at `0x0100`** (EIP-7951). This verifies the signature curve that
  Apple/Android **passkeys** use, so you can build "sign in with Face ID, no seed
  phrase" wallets with on-chain verification. For a consumer app demo this is a
  genuinely strong card to play.
- **EIP-7702 delegation** is supported (EOAs can temporarily act as smart accounts) with
  two Monad-specific rules: a delegated EOA can't go below **10 MON**, and while acting
  as a contract, `CREATE`/`CREATE2` are banned.
- **No blob transactions** (EIP-4844, type 3).

### RPC differences that will bite your frontend

Because execution trails consensus, Monad exposes *three* views of the chain and the
block tag you pick is a real product decision:

| Tag | State | Meaning |
|---|---|---|
| `latest` | Proposed | Speculative execution, no consensus vote yet. Lowest latency. |
| `safe` | Voted | Supermajority-backed. Reverting takes extraordinary conditions. |
| `finalized` | Finalized | Irreversible short of a hard fork. Use for settlement. |

`pending` behaves like `latest`. Blocks move `Proposed → Voted → Finalized → Verified`,
and can skip `Voted` when consensus outruns execution.

Also:

- **`monadNewHeads` and `monadLogs`** are Monad-only websocket subscriptions that fire
  at *Proposed* — roughly a second earlier than the standard `newHeads`/`logs`, which
  fire at *Voted*. They carry extra `blockId` and `commitState` fields. For a
  real-time UI, these are how you get the snappy feel; just be ready for a proposed
  block to be abandoned.
- **`newPendingTransactions` and `syncing` subscriptions don't exist.** No global
  mempool means nothing to subscribe to.
- **`eth_getLogs` is range-limited** — 100 blocks on QuickNode / Monad Foundation
  endpoints, 1,000 on Alchemy and Ankr (Alchemy also caps at 10,000 logs). At 300 ms
  blocks, 100 blocks is 30 seconds of history. Backfilling a day means 288,000 blocks.
  **If your app needs history, you need an indexer.** Plan for it.
- **Deferred nonce/balance validation** — `eth_sendRawTransaction` may *accept* a
  transaction with a nonce gap or insufficient balance, because validation happens
  later. Acceptance is not success. Wait for the receipt.
- `eth_getTransactionByHash` returns `null` until inclusion, and the `blockNumber` it
  reports can change between calls before finality.
- Debug tracing requires an explicit trace options object and defaults to `callTracer`.

---

## 7. What this makes possible — and what it means for the Blitz

The judging criteria reward *"innovative mechanics… especially ones that leverage
Monad's potential."* So the question isn't "what app should I build," it's **"what
mechanic is absurd on Ethereum and fine here?"**

Sub-second finality and cheap execution move three walls:

**Transactions can be part of the interaction loop, not a checkout step.** At 12-second
blocks, every write is a modal with a spinner and users batch their actions. At
sub-second, a transaction can be a click. Real-time multiplayer, live auctions where
bids settle visibly, tick-based games, anything where the *latency itself* is the demo.

**State can be fine-grained.** On Ethereum you push state off-chain and settle
occasionally because each write is dollars. Here you can keep per-entity, per-tick,
per-move state on-chain. "This whole simulation runs on-chain and you can verify every
step" is a strong three-minute demo and impossible on most chains.

**Computation can be non-trivial.** Linear memory pricing up to 8 MB and a 30M
per-transaction gas limit mean on-chain work that would be laughable elsewhere —
a physics step, a pathfind, a sort over real data.

Concretely, for a 3-minute live demo, the strongest shapes are:

1. **Something that visibly ticks.** Put a live counter of on-chain transactions on
   screen and let the audience see state change as fast as you click. Latency is the
   most legible possible proof of the platform.
2. **Something with a per-user or per-object state shard**, so throughput is real
   rather than serialized behind one hot slot.
3. **Passkey login via the P256 precompile**, if you want the "this feels like a normal
   app" moment — no seed phrase, Face ID, done.
4. **A mechanic that's honestly impossible elsewhere** — and say the number on stage.
   "This is 40 transactions per player per minute. On Ethereum that's $X and 8 minutes."

And the anti-patterns for this specific event: a clone with a nicer UI, an app where
the chain is just a database, and anything whose demo requires you to explain it for
two of your three minutes.

---

## 8. Traps checklist, before you ship

- [ ] Explicit `gas` on every write from the frontend — you pay the limit, not the usage.
- [ ] No unbounded loops over user-growable arrays.
- [ ] Checks → effects → interactions, everywhere you touch an external address.
- [ ] Nothing secret in storage. `private` is not private.
- [ ] Randomness is either a real VRF or an admitted joke.
- [ ] UI reads `latest` for speed, but anything that matters waits for `finalized`.
- [ ] History comes from an indexer or live subscription, not a wide `eth_getLogs`.
- [ ] A transaction being accepted ≠ succeeded. Always await the receipt.
- [ ] No private keys, `.env` values, or RPC keys in commits — the repo is public.
- [ ] Contract address + live URL in `README.md`.

---

## Sources

- [Monad Documentation](https://docs.monad.xyz/)
- [Network Information](https://docs.monad.xyz/getting-started/network-information)
- [Differences between Monad and Ethereum](https://docs.monad.xyz/developer-essentials/differences)
- [Gas Pricing](https://docs.monad.xyz/developer-essentials/gas-pricing)
- [Opcode Pricing](https://docs.monad.xyz/developer-essentials/opcode-pricing)
- [RPC Differences](https://docs.monad.xyz/reference/rpc-differences)
- [Verify a smart contract using Foundry](https://docs.monad.xyz/getting-started/verify-smart-contract/foundry)
- [foundry-monad template](https://github.com/monad-developers/foundry-monad)
- [Monad Developer Portal](https://developers.monad.xyz/)
- [Monad Faucet](https://faucet.monad.xyz/)
