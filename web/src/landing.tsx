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
 *  here carries information. */
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

const delay = (seconds: number) => ({ "--d": `${seconds}s` }) as CSSProperties;

/** Line-art glyphs, hand-drawn like the charts and for the same reason: an
 *  icon font is a network dependency on a page whose entire argument is that
 *  it does not need anyone else's server. */
function Glyph({ name }: { name: "mail" | "key" | "block" | "eye" }) {
  const shapes = {
    mail: (
      <>
        <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
        <path d="M3.5 7l8.5 6 8.5-6" />
      </>
    ),
    key: (
      <>
        <circle cx="8" cy="12" r="4.2" />
        <path d="M12.2 12H21M18 12v3.4M15.2 12v2.4" />
      </>
    ),
    block: (
      <>
        <path d="M12 2.8l8 4.6v9.2l-8 4.6-8-4.6V7.4z" />
        <path d="M4 7.4l8 4.6 8-4.6M12 12v9.2" />
      </>
    ),
    eye: (
      <>
        <path d="M1.8 12S5.4 5.6 12 5.6 22.2 12 22.2 12 18.6 18.4 12 18.4 1.8 12 1.8 12z" />
        <circle cx="12" cy="12" r="3.1" />
      </>
    ),
  };
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.35"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {shapes[name]}
    </svg>
  );
}

/** The hero's right half: one statement, checked on a loop.
 *
 *  It is the whole product in six lines. An email nobody asked the bank to
 *  send, a signature header, two numbers, and a verdict that lands a beat
 *  later. Pure CSS, no state, decorative to a screen reader. */
function ProofCard() {
  return (
    <div className="proof-card reveal" style={delay(0.22)} aria-hidden>
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
        <span className="proof-wait mono">checking RSA…</span>
        <span className="proof-ok">
          <span className="proof-tick" />
          SOURCE SIGNED
        </span>
      </div>
    </div>
  );
}

/** Twelve months as twelve marks. Solid is a signature, dashed is somebody's
 *  keyboard. The dashed one is the whole argument of that section, so it keeps
 *  breathing after the rest have settled. */
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
          <p className="hero-lede reveal" style={delay(0.08)}>
            Your broker already signed the real one. It has been sitting in your inbox
            this whole time.
          </p>
          <div className="hero-cta reveal" style={delay(0.16)}>
            <a className="cta" href={DEMO_LINK}>
              See a signed record
              <span aria-hidden> →</span>
            </a>
            <a className="cta cta-ghost" href="/manage">
              Sign in as a fund or a PM
            </a>
          </div>
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
          <h2>Three ways to prove a number. Two don't work.</h2>
        </div>
        <div className="opts">
          <div className="opt opt-bad reveal">
            <span className="opt-mark">✕</span>
            <h3>A PDF</h3>
            <p className="small muted">The manager typed it himself.</p>
          </div>
          <div className="opt opt-bad reveal" style={delay(0.08)}>
            <span className="opt-mark">✕</span>
            <h3>Our word for it</h3>
            <p className="small muted">
              A platform vouching for its own customer proves nothing.
            </p>
          </div>
          <div className="opt opt-good reveal" style={delay(0.16)}>
            <span className="opt-mark opt-mark-on">✓</span>
            <h3>The DKIM signature</h3>
            <p className="small muted">Already sent. Nobody had to agree to anything.</p>
          </div>
        </div>
      </section>

      {/* 2. What we do with it. Four steps because there are four. */}
      <section className="section">
        <div className="section-head reveal">
          <div className="eyebrow">How it works</div>
          <h2>Four steps. The bank never finds out.</h2>
        </div>
        <ol className="flow">
          <li className="flow-step reveal">
            <span className="flow-icon">
              <Glyph name="mail" />
            </span>
            <div className="flow-n">01</div>
            <h3>Forward the statement</h3>
            <p className="small muted">The email your broker already sends.</p>
          </li>
          <li className="flow-step reveal" style={delay(0.08)}>
            <span className="flow-icon">
              <Glyph name="key" />
            </span>
            <div className="flow-n">02</div>
            <h3>Check the signature</h3>
            <p className="small muted">
              Real RSA, and we copy the DNS key down before it retires.
            </p>
          </li>
          <li className="flow-step reveal" style={delay(0.16)}>
            <span className="flow-icon">
              <Glyph name="block" />
            </span>
            <div className="flow-n">03</div>
            <h3>Anchor on Monad</h3>
            <p className="small muted">
              Every ingest. 0.3s blocks, so we prove the moment, not the day.
            </p>
          </li>
          <li className="flow-step reveal" style={delay(0.24)}>
            <span className="flow-icon">
              <Glyph name="eye" />
            </span>
            <div className="flow-n">04</div>
            <h3>They check it without us</h3>
            <p className="small muted">47 leaves re-folded in the allocator's browser.</p>
          </li>
        </ol>
      </section>

      {/* 3. The punchline. Same number, different evidence, one glance. */}
      <section className="section">
        <div className="section-head reveal">
          <div className="eyebrow">Why it bites</div>
          <h2>One typed row costs the whole year.</h2>
        </div>
        <div className="versus">
          <a className="vs-card reveal" href={`/view/${DEMO_INVITES[0].token}`}>
            <div className="vs-name">Meridian Global Macro</div>
            <div className="vs-value">+21.89%</div>
            <div className="vs-sub">annualized TWR, net</div>
            <Ticks />
            <div className="vs-foot">
              <span className="badge badge-source_signed">
                <span className="dot" />
                source signed
              </span>
              <span className="small muted">12 signed</span>
            </div>
          </a>
          <a className="vs-card reveal" style={delay(0.1)} href={`/view/${DEMO_INVITES[1].token}`}>
            <div className="vs-name">Northwind Partners</div>
            <div className="vs-value">+21.89%</div>
            <div className="vs-sub">annualized TWR, net</div>
            <Ticks typed={7} />
            <div className="vs-foot">
              <span className="badge badge-self_reported">
                <span className="dot" />
                self reported
              </span>
              <span className="small muted">11 signed, 1 typed</span>
            </div>
          </a>
        </div>
        <p className="vs-caption small muted reveal">
          Identical to the digit. A metric carries the weakest evidence that fed it.
        </p>
      </section>

      {/* 4. Three seats. Which door you came through decides what exists, so
             the doors are left to say it themselves. */}
      <section className="section">
        <div className="three-doors">
          <a className="door door-fund reveal" href="/manage">
            <div className="door-role">Sign in as</div>
            <div className="door-name">The fund</div>
            <p className="small muted">Every pod, and the only seat that can add one.</p>
            <span className="arrow" aria-hidden>
              →
            </span>
          </a>
          <a className="door door-pm reveal" style={delay(0.08)} href="/manage">
            <div className="door-role">Sign in as</div>
            <div className="door-name">A manager</div>
            <p className="small muted">One book. The pod next door 404s.</p>
            <span className="arrow" aria-hidden>
              →
            </span>
          </a>
          <a className="door door-allocator reveal" style={delay(0.16)} href={DEMO_LINK}>
            <div className="door-role">No account</div>
            <div className="door-name">An allocator</div>
            <p className="small muted">One link. Watermarked, and revocable mid call.</p>
            <span className="arrow" aria-hidden>
              →
            </span>
          </a>
        </div>

        {DEMO_INVITES.map((invite, i) => (
          <a
            className="record-link reveal"
            key={invite.token}
            href={`/view/${invite.token}`}
            style={delay(0.04 * i)}
          >
            <div>
              <div className="name">{invite.record}</div>
              <div className="small muted">{invite.blurb}</div>
            </div>
            <span className="pill">{PROFILE_LABELS[invite.profile]}</span>
          </a>
        ))}
      </section>

      {/* Only when there is something to point at. An instance with no
          registry says nothing here rather than explaining its own absence. */}
      {config.data?.registry_address && (
        <p className="small muted">
          Chain {config.data.chain_id} ·{" "}
          <a href={`${config.data.explorer_url}/address/${config.data.registry_address}`}>
            {config.data.registry_address}
          </a>
        </p>
      )}
    </Page>
  );
}
