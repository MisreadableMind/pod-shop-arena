import { useEffect, type CSSProperties } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "./api";
import { useTitle } from "./components";
import { DEMO_INVITES, PROFILE_LABELS } from "./demo";
import { Page } from "./shell";

/** Scroll reveal, in about a dozen lines instead of a library.
 *
 *  Anything that should arrive rather than simply be there carries `.reveal`;
 *  this adds `.in` the first time it crosses into view and then stops watching
 *  it. A `--d` custom property on the element staggers siblings.
 *
 *  Reduced-motion visitors get the finished state on mount. That is the same
 *  page with the theatre switched off, which is the point: none of the motion
 *  below carries information. */
function useReveal() {
  useEffect(() => {
    const nodes = Array.from(document.querySelectorAll<HTMLElement>(".reveal"));
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (still || !("IntersectionObserver" in window)) {
      nodes.forEach((node) => node.classList.add("in"));
      return;
    }
    const watcher = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.classList.add("in");
          watcher.unobserve(entry.target);
        }
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" },
    );
    nodes.forEach((node) => watcher.observe(node));
    return () => watcher.disconnect();
  }, []);
}

const DEMO_LINK = `/view/${DEMO_INVITES[0].token}`;

/** The hero's right half: one statement, checked on a loop.
 *
 *  It is the whole product in six lines. An email nobody asked the bank to
 *  send, a signature header, two numbers, and a verdict that arrives a beat
 *  later. Pure CSS, no state, decorative to a screen reader. */
function ProofCard() {
  return (
    <div className="proof-card reveal" style={{ "--d": "0.24s" } as CSSProperties} aria-hidden>
      <div className="proof-head">
        <span className="mono">statement-2025-11.eml</span>
        <span className="proof-from">sent by your broker</span>
      </div>

      <div className="proof-sig mono">
        DKIM-Signature: v=1; a=rsa-sha256; c=relaxed/relaxed;
        d=ibkr-demo.podarena.test; s=mail2024; bh=T5hK9x…
      </div>

      <div className="proof-rows">
        <div className="proof-row">
          <span>Net asset value</span>
          <b>$41,207,338.22</b>
        </div>
        <div className="proof-row">
          <span>Annualized TWR, net</span>
          <b>+21.89%</b>
        </div>
      </div>

      <div className="proof-verdict">
        <span className="proof-wait mono">checking RSA against the captured key…</span>
        <span className="proof-ok">
          <span className="proof-tick" />
          SOURCE SIGNED
        </span>
      </div>
    </div>
  );
}

/** Twelve months as twelve marks. Solid is a signature, hollow is somebody's
 *  keyboard. The hollow one is the entire argument of that section, so it gets
 *  to keep pulsing after the rest have settled. */
function Ticks({ typed }: { typed?: number }) {
  return (
    <div className="ticks">
      {Array.from({ length: 12 }).map((_, i) => (
        <span
          key={i}
          className={`tick ${i === typed ? "typed" : ""}`}
          style={{ "--i": i } as CSSProperties}
        />
      ))}
    </div>
  );
}

export function Home() {
  useTitle("PodShop Arena");
  useReveal();
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });

  const hero = (
    <section className="hero">
      <div className="hero-inner hero-grid">
        <div>
          <h1 className="reveal">Anyone can type a track record.</h1>
          <p className="hero-lede reveal" style={{ "--d": "0.08s" } as CSSProperties}>
            Which is why an allocator cannot tell your twelve good months from twelve
            numbers you invented on a Tuesday. Your broker already signs every statement
            it emails you. We read that signature, and hand the allocator a record they
            can check without asking us anything.
          </p>
          <div className="hero-cta reveal" style={{ "--d": "0.16s" } as CSSProperties}>
            <a className="cta" href={DEMO_LINK}>
              See a signed record
              <span aria-hidden> →</span>
            </a>
            <a className="cta cta-ghost" href="/manage">
              Sign in as a fund or a PM
            </a>
          </div>
          <p className="cta-note reveal" style={{ "--d": "0.22s" } as CSSProperties}>
            Everything is pre loaded. No account, no wallet, nothing to install.
          </p>
        </div>
        <ProofCard />
      </div>
    </section>
  );

  return (
    <Page hero={hero}>
      {/* 1. The problem, as the three things an allocator can actually do. */}
      <section className="section">
        <div className="section-head reveal">
          <div className="eyebrow">The problem</div>
          <h2>An allocator has three options. Two of them don't work.</h2>
        </div>
        <div className="opts">
          <div className="opt reveal">
            <span className="opt-mark">✕</span>
            <h3>Take the PDF on faith</h3>
            <p className="small muted">
              Twelve good months in a document the manager produced himself. Every figure
              on it is a claim. Nothing on it can be checked by the person being asked to
              wire the money.
            </p>
          </div>
          <div className="opt reveal" style={{ "--d": "0.08s" } as CSSProperties}>
            <span className="opt-mark">✕</span>
            <h3>Ask the bank to cooperate</h3>
            <p className="small muted">
              An API, a data feed, a letter on headed paper. This is what every existing
              fix asks for, and it is why every existing fix stalls. Goldman is not going
              to sign your letter.
            </p>
          </div>
          <div className="opt opt-good reveal" style={{ "--d": "0.16s" } as CSSProperties}>
            <span className="opt-mark opt-mark-on">✓</span>
            <h3>Read the signature already there</h3>
            <p className="small muted">
              Every statement email carries a DKIM signature: the bank's own key, over the
              exact bytes, applied years ago without anyone thinking about it. Nobody has
              to agree to anything. The proof is sitting in your inbox.
            </p>
          </div>
        </div>
      </section>

      {/* 2. What we do with it. Four steps because there are four. */}
      <section className="section">
        <div className="section-head reveal">
          <div className="eyebrow">How it works</div>
          <h2>Four steps, and the bank never finds out.</h2>
        </div>
        <ol className="flow">
          <li className="flow-step reveal">
            <span className="flow-n">01</span>
            <h3>The email arrives</h3>
            <p className="small muted">
              The monthly statement your broker already sends. You forward it. There is no
              integration to request and nobody to ask.
            </p>
          </li>
          <li className="flow-step reveal" style={{ "--d": "0.08s" } as CSSProperties}>
            <span className="flow-n">02</span>
            <h3>The signature gets checked</h3>
            <p className="small muted">
              Real RSA against the DKIM header. We also copy down the DNS key exactly as it
              stands today, because keys get retired, and a copy taken now is what keeps
              this signature checkable in five years.
            </p>
          </li>
          <li className="flow-step reveal" style={{ "--d": "0.16s" } as CSSProperties}>
            <span className="flow-n">03</span>
            <h3>The root lands on Monad</h3>
            <p className="small muted">
              Every ingest, not a nightly batch. Blocks confirm in 0.3 seconds, so we anchor
              the moment rather than the day, and a month quietly dropped later leaves a
              numbered gap anyone can count.
            </p>
          </li>
          <li className="flow-step reveal" style={{ "--d": "0.24s" } as CSSProperties}>
            <span className="flow-n">04</span>
            <h3>The allocator checks it alone</h3>
            <p className="small muted">
              Their browser re folds all 47 Merkle leaves itself and reads the root off an
              RPC they typed in. Our server is not in the trust path, and the offline bundle
              does not need us at all.
            </p>
          </li>
        </ol>
      </section>

      {/* 3. The punchline. Same number, different evidence, and the whole
             disagreement is visible in one glance. */}
      <section className="section">
        <div className="section-head reveal">
          <div className="eyebrow">Why it bites</div>
          <h2>One typed row costs you the whole year.</h2>
        </div>
        <div className="versus">
          <a className="vs-card reveal" href={`/view/${DEMO_INVITES[0].token}`}>
            <div className="vs-name">Meridian Global Macro</div>
            <div className="vs-value">+21.89%</div>
            <div className="vs-sub">annualized TWR, net of fees</div>
            <Ticks />
            <div className="vs-foot">
              <span className="badge badge-source_signed">
                <span className="dot" />
                source signed
              </span>
              <span className="small muted">twelve statements, twelve signatures</span>
            </div>
          </a>
          <a className="vs-card reveal" style={{ "--d": "0.1s" } as CSSProperties} href={`/view/${DEMO_INVITES[1].token}`}>
            <div className="vs-name">Northwind Partners</div>
            <div className="vs-value">+21.89%</div>
            <div className="vs-sub">annualized TWR, net of fees</div>
            <Ticks typed={7} />
            <div className="vs-foot">
              <span className="badge badge-self_reported">
                <span className="dot" />
                self reported
              </span>
              <span className="small muted">eleven signed, one month typed in</span>
            </div>
          </a>
        </div>
        <p className="vs-caption small muted reveal">
          Identical to the last digit, <span className="mono">0.218937808100</span>. A metric
          carries the weakest evidence that fed it, so a single unverifiable month caps a
          year of proof. That will feel punitive to a customer, and it is exactly right.
          Open both and compare.
        </p>
      </section>

      {/* 4. Three seats. Which door you came through decides what exists. */}
      <section className="section">
        <div className="section-head reveal">
          <div className="eyebrow">The demo</div>
          <h2>Pick a seat. The product changes shape depending on which one.</h2>
        </div>
        <div className="three-doors">
          <a className="door door-fund reveal" href="/manage">
            <div className="door-role">Sign in as</div>
            <div className="door-name">The fund</div>
            <p className="small muted">
              The platform's seat. The whole roster, every key any pod has handed out, and
              the only seat that can take a new pod on.
            </p>
            <span className="arrow" aria-hidden>
              →
            </span>
          </a>
          <a
            className="door door-pm reveal"
            style={{ "--d": "0.08s" } as CSSProperties}
            href="/manage"
          >
            <div className="door-role">Sign in as</div>
            <div className="door-name">A portfolio manager</div>
            <p className="small muted">
              One book. The pod next door does not exist from this seat, and the refusal is
              a 404 rather than a 403, because saying "not yours" leaks the roster one guess
              at a time.
            </p>
            <span className="arrow" aria-hidden>
              →
            </span>
          </a>
          <a
            className="door door-allocator reveal"
            style={{ "--d": "0.16s" } as CSSProperties}
            href={DEMO_LINK}
          >
            <div className="door-role">No account at all</div>
            <div className="door-name">An allocator</div>
            <p className="small muted">
              Outside the wall. One link, tied to your address, stamped with your name,
              killable in the middle of a conversation.
            </p>
            <span className="arrow" aria-hidden>
              →
            </span>
          </a>
        </div>

        <p className="small muted reveal" style={{ margin: "0 0 14px" }}>
          Sign in is one click: the console shows a button per seat and the box arrives with
          the token already in it. Or skip it and walk in as an allocator, through one of
          these four keys.
        </p>

        {DEMO_INVITES.map((invite, i) => (
          <a
            className="record-link reveal"
            key={invite.token}
            href={`/view/${invite.token}`}
            style={{ "--d": `${0.04 * i}s` } as CSSProperties}
          >
            <div>
              <div className="name">{invite.record}</div>
              <div className="small muted">{invite.blurb}</div>
            </div>
            <span className="pill">{PROFILE_LABELS[invite.profile]}</span>
          </a>
        ))}
      </section>

      <p className="small muted">
        Chain {config.data?.chain_id} ·{" "}
        {config.data?.registry_address ? (
          <a href={`${config.data.explorer_url}/address/${config.data.registry_address}`}>
            {config.data.registry_address}
          </a>
        ) : (
          "no registry configured, so roots are computed but not anchored"
        )}
      </p>
    </Page>
  );
}
