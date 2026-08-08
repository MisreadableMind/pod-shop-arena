import { useEffect, useMemo, useState } from "react";
import type { Evidence, Leaf, Metric, RecordView, Tier } from "./api";
import { api } from "./api";
import { readAnchoredRoot, rebuildRoot, verifyProof } from "./verify";

// -- formatting -----------------------------------------------------------

const RATIO_AS_PERCENT = new Set([
  "twr_cumulative",
  "twr_annualized",
  "modified_dietz",
  "max_drawdown",
  "volatility_annualized",
  "var_historical",
]);

const LABELS: Record<string, string> = {
  twr_cumulative: "Cumulative TWR",
  twr_annualized: "Annualized TWR",
  modified_dietz: "Modified Dietz",
  max_drawdown: "Max drawdown",
  volatility_annualized: "Volatility",
  sharpe: "Sharpe",
  sortino: "Sortino",
  calmar: "Calmar",
  var_historical: "VaR 95%",
};

// Metrics where the direction is the point. The design system is achromatic —
// no red/green — so an explicit leading + is what tells a gain from a loss.
const SIGNED = new Set(["twr_cumulative", "twr_annualized", "modified_dietz"]);

export function formatMetric(metric: Metric): string {
  const value = Number(metric.value);
  const sign = SIGNED.has(metric.key) && value > 0 ? "+" : "";
  if (RATIO_AS_PERCENT.has(metric.key)) {
    return `${sign}${(value * 100).toFixed(2)}%`;
  }
  return `${sign}${value.toFixed(2)}`;
}

// Mirrors core/money.py. Two decimals is right far more often than it is
// wrong, but yen has none and a hardcoded /100 would show a fund a hundred
// times poorer than it is.
const MINOR_EXPONENTS: Record<string, number> = {
  JPY: 0,
  KRW: 0,
  BTC: 8,
  ETH: 18,
};

export function money(minor: number, currency: string): string {
  const exponent = MINOR_EXPONENTS[currency.toUpperCase()] ?? 2;
  const major = minor / 10 ** exponent;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(major);
}

function shortHex(hex: string, size = 10): string {
  return `${hex.slice(0, size)}…${hex.slice(-4)}`;
}

// -- tier -----------------------------------------------------------------

/** The trust hierarchy is encoded by weight, not hue: solid fill for the
 *  strongest evidence, then outline, then quiet outline, then greyed. A
 *  colour-blind allocator reads the same ranking a colour-sighted one does. */
export function TierBadge({ tier, label }: { tier: Tier; label?: string }) {
  return (
    <span className={`badge badge-${tier}`}>
      <span className="dot" />
      {label ?? tier.replace(/_/g, " ")}
    </span>
  );
}

// -- metrics --------------------------------------------------------------

export function MetricGrid({ metrics, basis }: { metrics: Metric[]; basis: "net" | "gross" }) {
  const shown = metrics.filter((m) => m.basis === basis);
  if (shown.length === 0) return null;

  return (
    <div className="grid">
      {shown.map((metric) => {
        const value = Number(metric.value);
        const tone =
          metric.key === "max_drawdown" || metric.key === "var_historical"
            ? "neg"
            : value > 0
              ? "pos"
              : value < 0
                ? "neg"
                : "";
        return (
          <div
            className="metric-tile"
            key={`${metric.key}-${metric.basis}`}
            title={metric.formula}
          >
            <div className="label">{LABELS[metric.key] ?? metric.key}</div>
            <div className={`value ${tone}`}>{formatMetric(metric)}</div>
            {/* Nothing is displayed without its tier next to it. */}
            <div className="sub">{metric.tier.replace(/_/g, " ")}</div>
          </div>
        );
      })}
    </div>
  );
}

// -- chart ----------------------------------------------------------------

// Tier is drawn, not coloured: filled disc for signed evidence, filled but
// lighter for attested, hollow for observed, hollow-and-faint for whatever
// somebody typed. Same ranking the badges use.
const DOT: Record<Tier, { fill: string; stroke: string; r: number }> = {
  source_signed: { fill: "var(--color-onyx)", stroke: "var(--color-onyx)", r: 3.4 },
  aggregator_attested: { fill: "var(--color-steel)", stroke: "var(--color-steel)", r: 3.2 },
  platform_observed: { fill: "var(--surface-card)", stroke: "var(--color-slate-veil)", r: 3.2 },
  self_reported: { fill: "var(--surface-card)", stroke: "var(--color-umber)", r: 3.8 },
};

/** Hand-rolled inline SVG, so the picture and the numbers cannot disagree.
 *  A charting library that silently interpolates or drops a point would be a
 *  second, unversioned interpretation of evidence we just went to a lot of
 *  trouble to pin down. */
export function NavChart({
  series,
  flows,
}: {
  series: Array<{ as_of: string; amount_minor: number; currency: string; tier: Tier }>;
  flows?: Array<{ as_of: string; amount_minor: number }>;
}) {
  if (series.length < 2) return null;

  const width = 720;
  const height = 220;
  const pad = { top: 16, right: 16, bottom: 26, left: 62 };

  const values = series.map((point) => point.amount_minor);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;

  const x = (i: number) =>
    pad.left + (i / (series.length - 1)) * (width - pad.left - pad.right);
  const y = (value: number) =>
    pad.top + (1 - (value - min) / span) * (height - pad.top - pad.bottom);

  const path = series.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.amount_minor)}`).join(" ");
  const area = `${path} L${x(series.length - 1)},${height - pad.bottom} L${x(0)},${height - pad.bottom} Z`;
  const currency = series[0].currency;

  const flowMarks = (flows ?? []).map((flow) => {
    const index = series.findIndex((p) => p.as_of >= flow.as_of);
    return { ...flow, index: index === -1 ? series.length - 1 : index };
  });

  return (
    <div className="chart-wrap">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Net asset value over time"
      >
        <defs>
          {/* The dawn arc draws the curve. It is the only colour on the page,
              and it is the same one on the hero and the brand mark. */}
          <linearGradient id="dawnarc" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--color-umber)" />
            <stop offset="54%" stopColor="var(--color-steel)" />
            <stop offset="100%" stopColor="var(--color-cream)" />
          </linearGradient>
          <linearGradient id="navfill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-steel)" stopOpacity="0.14" />
            <stop offset="100%" stopColor="var(--color-steel)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {[0, 0.5, 1].map((fraction) => {
          const value = min + fraction * span;
          return (
            <g key={fraction}>
              <line
                x1={pad.left}
                x2={width - pad.right}
                y1={y(value)}
                y2={y(value)}
                stroke="var(--hairline)"
              />
              <text
                x={pad.left - 8}
                y={y(value) + 4}
                textAnchor="end"
                fill="var(--text-dim)"
                fontSize="10"
                fontFamily="var(--font-mono)"
              >
                {money(value, currency)}
              </text>
            </g>
          );
        })}

        <path d={area} fill="url(#navfill)" />
        <path
          d={path}
          fill="none"
          stroke="url(#dawnarc)"
          strokeWidth="2.25"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {series.map((point, i) => {
          const dot = DOT[point.tier];
          return (
            <circle
              key={point.as_of}
              cx={x(i)}
              cy={y(point.amount_minor)}
              r={dot.r}
              fill={dot.fill}
              stroke={dot.stroke}
              strokeWidth="1.4"
            >
              <title>
                {point.as_of} · {money(point.amount_minor, currency)} · {point.tier}
              </title>
            </circle>
          );
        })}

        {/* Deposits and withdrawals differ by dash pattern, not by colour. */}
        {flowMarks.map((flow) => (
          <line
            key={`${flow.as_of}-${flow.amount_minor}`}
            x1={x(flow.index)}
            x2={x(flow.index)}
            y1={pad.top}
            y2={height - pad.bottom}
            stroke="var(--color-onyx)"
            strokeDasharray={flow.amount_minor > 0 ? "5 4" : "1.5 4"}
            strokeOpacity="0.34"
          >
            <title>
              {flow.amount_minor > 0 ? "Deposit" : "Withdrawal"} {flow.as_of}
            </title>
          </line>
        ))}

        <text
          x={pad.left}
          y={height - 8}
          fill="var(--text-dim)"
          fontSize="10"
          fontFamily="var(--font-mono)"
        >
          {series[0].as_of}
        </text>
        <text
          x={width - pad.right}
          y={height - 8}
          textAnchor="end"
          fill="var(--text-dim)"
          fontSize="10"
          fontFamily="var(--font-mono)"
        >
          {series[series.length - 1].as_of}
        </text>
      </svg>
      <p className="chart-note">
        Long dashes are deposits, fine dashes are withdrawals. Filled points are signed by
        the bank; hollow ones are weaker. Compute a return from the line alone and you'll
        get it wrong everywhere money moved, which is why we don't.
      </p>
    </div>
  );
}

// -- evidence -------------------------------------------------------------

/** `token` is null in the manager's preview, where there is no invite to
 *  download against — the row still renders, the link does not. */
export function EvidenceTable({
  evidence,
  token,
}: {
  evidence: Evidence[];
  token: string | null;
}) {
  return (
    <table>
      <thead>
        <tr>
          <th>Document</th>
          <th>Signature</th>
          <th>Captured key</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {evidence.map((item) => {
          const dkim = item.dkim;
          const ignored = (dkim?.signatures ?? []).filter((s) => !s.considered);
          return (
            <tr key={item.sha256}>
              <td>
                <div>{item.filename ?? item.sha256.slice(0, 16)}</div>
                <div className="small muted mono">{shortHex(item.sha256, 16)}</div>
                <div className="small muted">{item.doc_type.replace(/_/g, " ")}</div>
              </td>
              <td>
                {dkim?.verified ? (
                  <TierBadge tier="source_signed" label="verified" />
                ) : (
                  <TierBadge tier="self_reported" label="not verified" />
                )}
                <div className="small muted mono" style={{ marginTop: 4 }}>
                  {dkim?.d_domain ?? "no signature"}
                  {dkim?.selector ? ` · ${dkim.selector}` : ""}
                </div>
                {dkim?.failure_reason && (
                  <div className="small muted" style={{ marginTop: 4, maxWidth: 380 }}>
                    {dkim.failure_reason}
                  </div>
                )}
                {ignored.map((sig) => (
                  <div key={sig.index} className="small muted" style={{ marginTop: 4, maxWidth: 380 }}>
                    Ignored {sig.domain}: {sig.reason}
                  </div>
                ))}
              </td>
              <td className="small mono muted">
                {dkim?.dns_txt_record ? (
                  <>
                    <div>{dkim.dns_txt_record.slice(0, 28)}…</div>
                    <div>captured {dkim.dns_captured_at?.slice(0, 10)}</div>
                  </>
                ) : (
                  "—"
                )}
              </td>
              <td>
                {token ? (
                  <a className="small" href={api.documentUrl(token, item.sha256)}>
                    .eml
                  </a>
                ) : (
                  <span className="small muted">.eml</span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// -- independent verification --------------------------------------------

type CheckState = "pending" | "running" | "ok" | "bad";

type Check = { name: string; state: CheckState; detail: string };

/** The panel that decides whether "verified" means anything.
 *  Every check here runs in this browser, against an RPC the viewer picks. */
export function VerifyPanel({
  view,
  token,
  chainId,
  defaultRpc,
  registry,
  chainKey,
}: {
  view: RecordView;
  token: string;
  chainId: number;
  defaultRpc: string;
  registry: string | null;
  chainKey: string | null;
}) {
  const [rpcUrl, setRpcUrl] = useState(defaultRpc);
  const [checks, setChecks] = useState<Check[]>([]);
  const [running, setRunning] = useState(false);

  const leaves: Leaf[] = view.merkle_leaves ?? [];

  const run = async () => {
    setRunning(true);
    const results: Check[] = [];
    const push = (check: Check) => {
      results.push(check);
      setChecks([...results]);
    };

    // 1. Does the published leaf set actually fold to the published root?
    try {
      const rebuilt = await rebuildRoot(leaves.map((leaf) => leaf.digest));
      const ok = rebuilt.toLowerCase() === view.snapshot.root.toLowerCase();
      push({
        name: `Re-fold all ${leaves.length} leaves`,
        state: ok ? "ok" : "bad",
        detail: ok
          ? `${rebuilt.slice(0, 20)}… computed here, in this tab`
          : `we computed ${rebuilt.slice(0, 20)}…, the server claims ${view.snapshot.root.slice(0, 20)}…`,
      });
    } catch (error) {
      push({ name: "Re-fold all leaves", state: "bad", detail: String(error) });
    }

    // 2. Does a server-supplied Merkle path agree with our own fold?
    try {
      const sample = leaves[0];
      const proof = await api.proof(token, sample.digest);
      const ok = await verifyProof(proof, view.snapshot.root);
      push({
        name: "Check a Merkle path",
        state: ok ? "ok" : "bad",
        detail: ok ? sample.label : "the path doesn't lead to the root",
      });
    } catch (error) {
      push({ name: "Check a Merkle path", state: "bad", detail: String(error) });
    }

    // 3. The one that matters: is that root on a chain we do not run?
    if (registry && chainKey) {
      try {
        const head = await readAnchoredRoot({
          rpcUrl,
          chainId,
          registry,
          recordKey: chainKey,
        });
        const ok = head.root.toLowerCase() === view.snapshot.root.toLowerCase();
        push({
          name: `Compare against chain ${chainId}`,
          state: ok ? "ok" : "bad",
          detail: ok
            ? `sequence ${head.seq}, anchored ${new Date(Number(head.ts) * 1000).toISOString().slice(0, 19)}Z`
            : `chain says ${head.root.slice(0, 20)}…`,
        });
      } catch (error) {
        push({
          name: `Compare against chain ${chainId}`,
          state: "bad",
          detail: `RPC call failed: ${String(error).slice(0, 120)}`,
        });
      }
    } else {
      push({
        name: "Compare against chain",
        state: "pending",
        detail: "this instance has no registry address configured, so nothing was anchored",
      });
    }

    setRunning(false);
  };

  const allOk = checks.length > 0 && checks.every((c) => c.state === "ok");

  return (
    <div className="card card-accent">
      <div className="card-head">
        <h2>Verify it yourself</h2>
        <span className="pill">runs in this browser</span>
      </div>
      <p className="lede">
        Every check below runs in this tab, on your machine. Point it at any Monad RPC you
        like. The whole idea is that ours isn't in the trust path.
      </p>

      <div className="row" style={{ marginBottom: 14 }}>
        <input
          type="text"
          value={rpcUrl}
          onChange={(event) => setRpcUrl(event.target.value)}
          aria-label="RPC endpoint"
        />
        <button onClick={run} disabled={running}>
          {running ? "Checking…" : "Run the checks"}
        </button>
      </div>

      {checks.map((check) => (
        <div className="check" key={check.name}>
          <span
            className={`mark ${check.state === "ok" ? "ok" : check.state === "bad" ? "bad" : "wait"}`}
          >
            {check.state === "ok" ? "PASS" : check.state === "bad" ? "FAIL" : "SKIP"}
          </span>
          <div>
            <div>{check.name}</div>
            <div className="small muted mono">{check.detail}</div>
          </div>
        </div>
      ))}

      {allOk && (
        <p className="verdict">All of it checked out, here. Nothing above took our word for anything.</p>
      )}

      <p className="small muted" style={{ marginTop: 16, marginBottom: 0 }}>
        Or don't trust this page either.{" "}
        <a href={api.bundleUrl(token)}>Download the bundle</a> — the .eml files, the DNS
        keys as we captured them, every Merkle proof — and run{" "}
        <code>podarena-verify bundle</code> on your own machine, offline.
      </p>
    </div>
  );
}

// -- watermark ------------------------------------------------------------

export function Watermark({ viewer, at }: { viewer: string; at: string }) {
  const text = useMemo(() => `${viewer} · ${at.slice(0, 19)}Z`, [viewer, at]);
  return (
    <div className="watermark" aria-hidden>
      <span>
        {Array.from({ length: 14 }).map((_, i) => (
          <span key={i}>
            {text}
            <br />
          </span>
        ))}
      </span>
    </div>
  );
}

export function useTitle(title: string) {
  useEffect(() => {
    document.title = title;
  }, [title]);
}
