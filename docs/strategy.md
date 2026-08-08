# Nobody wants to be verified

**Pod Arena · Strategy memo · August 2026 · Internal, draft**

Here's what I think we're actually selling, who pays for it, how much, and what has to
be true if we want $50M in three to five years.[^1]

Companion files: the print version of this memo is [`strategy.html`](./strategy.html);
the deck we show is [`deck/index.html`](./deck/index.html).

---

## 01 · Demand

Portfolio managers want money. Allocators want to spend less time on diligence.
Verification is the toll booth between them, and a toll booth is an excellent thing to
own.

SOC 2 is the same shape. Nobody wants the report. It costs six figures, improves nothing
a customer can see, and companies buy it because their buyers stopped signing without
one. That's what Vanta built on.[^2]

> **The allocator creates the demand.**
> **The manager pays the bill.**

We are not going to persuade managers that verification is good for them. The job is to
get a small number of allocators people take seriously to say four words: *send it
through Pod Arena*. Then we sell everyone in their pipeline the ability to comply.

### Blockchain

- **Do** keep the anchoring and the ZK proofs. They are cheap and they work.
- **Do** sell one sentence: *an independent party pulled this straight from the
  administrator, and nobody could touch it.*
- **Don't** lead with "blockchain" in front of an allocator. In that room it is a reason
  to stop listening, not a moat. The Merkle root is *how*, not *what*.

---

## 02 · Our ICP

Allocators create the demand but do not pay first: long cycles, no deadline, no real
budget for sourcing managers. The order below matters more than the list.

### 01 · The payer — a manager running $12–300M who is raising right now

Twelve to thirty-six months of live track, a real administrator, and a tearsheet in
Excel that gets discounted the moment an allocator opens it. Every DDQ eats six weeks.
They have a deadline and a budget line that already says *fundraising*. That's the whole
ICP in one word: **deadline**.

**$950–2,950 / mo**

### 02 · The demand-maker — emerging-manager programs, seeders, funds of funds, family offices, external allocation desks

Maybe forty of them worldwide matter. Give them the product almost free for eighteen
months. We aren't buying revenue from them. We're buying one sentence on their
submission page: *we accept Pod Arena records.* Charge in year two, once the pipeline
already runs through us.

**Free → $35–90k / yr from Y2**

### 03 · The multiplier — fund administrators

SS&C, Citco, Apex, Alter Domus, IQ-EQ. They hold the data already, and all of them are
climbing up-stack into GP services. White-label us across their emerging-manager book
and one signature is worth two hundred managers. Start in year two, because it's also
the conversation where somebody buys us.

**$120–350k / yr + rev share**

### Why not employers

**Employers vetting PM candidates.** It looks like the sharpest pain in the industry, and
it is. Nobody can check whether a candidate really ran $500M at 1.8 Sharpe. But that P&L
belongs to the old employer, who will never hand it over. Nothing to connect to.

### Crypto funds

Read-only exchange keys take ten minutes. No prime broker, no SFTP. And nobody distrusts
a track record more than a crypto allocator. Paying customers within a month. Small
cheques and a worse story for a buyer, so take it for proof, not as the plan.

---

## 03 · What we sell

| Line | Price | Note |
| --- | --- | --- |
| Manager subscription | $0.95–2.95k / mo | By connections and records |
| Per-raise data room | $12–35k | Comes out of the raise, not IT |
| Allocator seats | $35–90k / yr | Year 2. Free before that |
| Administrator deal | $120–350k / yr | Year 3. The step-change |

A $50M exit needs roughly **$7–9.5M of ARR** growing 60%+, at six to eight times
revenue. Get two strategic buyers in the room and $5–6M does it.

### The ramp (ARR, $M)

| | Y1 | Y2 | Y3 | **Y4** | Y5 |
| --- | --- | --- | --- | --- | --- |
| ARR | 0.35 | 1.4 | 4.0 | **8.0** | 13 |
| Managers | 30 | 110 | 260 | **480 · sell here** | 700 |

### How much to raise

**Cap the raise at $6–7M.** Pre-seed $1.2M, seed $4.8M, then stop.

A $18M round makes a $50M exit unacceptable to the board. The size of the round sets the
floor on an acceptable outcome before we have sold anything. The alternative is a small
round, most of the company retained, and a strategic buyer. On that path we probably
could not raise from a growth fund.

### Who buys us

Fund administrators first. They want the data layer and the GP relationship. Then
allocator tech: ION, Nasdaq, With Intelligence, Canoe, Allvue. Then fundraising
plumbing: Carta, Juniper Square, Passthrough.

The multiple depends on how many buyers are in the room, not on how good the product is.
Two bidders is 10×. One is 5×.

---

## 04 · Order of implementation

Ordered by what blocks us soonest.

1. **A written regulatory opinion in all three jurisdictions.** We need counsel in the
   UK, EU and US to state on paper that we are a technology provider, not an adviser and
   not a broker-dealer. The entity, the contracts, and every claim the product is
   allowed to make hang off that one classification. Nothing else can be committed until
   it is written down. — *$50–85k · 8–12 wks · this week*
2. **Two or three fund administrators.** Plaid has no place here — it is US retail
   banking and reaches none of the people we sell to. Administrators hold the data *and*
   their client list is our ICP. Everything else is IBKR Flex and SFTP.
3. **SOC 2 Type II and ISO 27001.** Nine months, so it starts in month one. No allocator
   lets us near a manager's data without them.
4. **An auditor's report on the maths.** An ISAE 3000 engagement on the calculation
   engine. It buys more trust than every proof mechanism in the codebase put together. —
   *$30–60k*
5. **Three allocators willing to say so in writing.** Without them there is no demand to
   sell against.
6. **An answer to "will my positions leak?"** Not ZK. That's year two. Year one it's
   architecture: positions never touch a path a viewer can reach, metrics only by
   default, embargo on. They have to feel it in the demo, not read it in a PDF.
7. **Insurance.** We publish claims about other people's numbers. One of them will be
   wrong eventually.

---

## 05 · Where we sell

> **Not EU or US. London or New York.**

London. English, the second-largest concentration of hedge funds, a workable regulator, a
dense community of seeders and emerging managers, and meetings we can reach without a
visa. Continental Europe on its own is too fragmented and too cheap to build $8M of ARR
on.

But build for the SEC Marketing Rule from day one anyway. It's the strictest regime,
retrofitting costs more, and our buyer is American. A company with 60–70% US revenue is
simply worth more to them.

**Order of operations.** EU parent. London, months 0–12. Delaware entity and one American
salesperson at month 12. Most new ARR from the US by year three.

---

## 06 · What we build, in order

The spec treats nearly everything as MVP. That's a three-year build, and we have about
nine months of runway at a time.

### Build now

Administrator ingestion → immutable snapshot → deterministic metrics → badge → the fence,
with its NDA gate, watermark and audit log → the disclaimer engine. **That's the
product.**

### Build next

ZK proofs. GIPS composites. Attribution. The attestor role. None of them closes the first
fifty customers, so none of them comes first.

### Build after that

Retail broker connectors: Robinhood, Coinbase, Schwab. Discovery marketplace. Reputation
graph. Peer cohorts. Hiring workflow. No money in them today, and no allocator has ever
asked.

---

[^1]: Every number here is a model, and every model is wrong. The useful question is
which direction, and we won't know until we try charging someone.

[^2]: The analogy limps in one place: SOC 2 became near-mandatory on its own, and nothing
forces an allocator to demand anything. Which is why the three signatures in §04 matter
more than the product.
