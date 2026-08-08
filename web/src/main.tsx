import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type RecordView } from "./api";
import {
  EvidenceTable,
  MetricGrid,
  NavChart,
  TierBadge,
  VerifyPanel,
  Watermark,
  money,
  useTitle,
} from "./components";
import "./styles.css";

const client = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

// Two routes and no library. A router that needs a code-generation step to
// serve `/` and `/view/:token` would be more machinery than the problem has.
function route(): { name: "home" } | { name: "view"; token: string } {
  const match = window.location.pathname.match(/^\/view\/([^/]+)/);
  return match ? { name: "view", token: match[1] } : { name: "home" };
}

function Masthead() {
  return (
    <header className="masthead">
      <a href="/" className="wordmark" style={{ color: "inherit" }}>
        Pod <span>Arena</span>
      </a>
      <div className="tagline">A track record the allocator can check themselves</div>
    </header>
  );
}

function DemoBanner() {
  return (
    <div className="banner">
      <strong>Everything here is synthetic.</strong> The messages are signed by a key
      generated when this instance was built, for a broker domain that does not exist. The
      cryptography is real and so are the verdicts — the broker is not.
    </div>
  );
}

function Home() {
  useTitle("Pod Arena");
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const records = useQuery({ queryKey: ["records"], queryFn: api.records });

  const demoLinks: Array<[string, string, string]> = [
    [
      "demo-meridian-full",
      "Meridian Global Macro",
      "Twelve months, every one of them signed by the broker's own key.",
    ],
    [
      "demo-northwind-full",
      "Northwind Partners",
      "The same twelve numbers, with one month typed into a spreadsheet. Watch what it costs.",
    ],
    [
      "demo-evidence-lab",
      "Evidence Lab",
      "Five ways a signature fails: a retired key, an l= tag, a flipped byte, a hand-forward, a stranger.",
    ],
  ];

  return (
    <div className="shell">
      <Masthead />
      {config.data?.demo_fixtures && <DemoBanner />}

      <h1>Nobody should have to take your word for it.</h1>
      <p className="hero-lede">
        A track record is worth nothing if the person it flatters typed it. Every fix on
        offer asks the institution to cooperate — an API, a data feed, a signed letter —
        and Goldman is not going to cooperate. So we work from what the institution
        already sends without agreeing to anything: the DKIM signature sitting on the
        statement email it mailed you years ago, without thinking about it.
      </p>

      <div className="card" style={{ marginTop: 28 }}>
        <h2>Start here</h2>
        <p className="lede">
          Pre-loaded records, so the demo starts on a full page instead of an empty form.
        </p>
        {demoLinks.map(([token, name, blurb]) => (
          <a className="record-link" key={token} href={`/view/${token}`}>
            <div className="name">{name}</div>
            <div className="small muted">{blurb}</div>
          </a>
        ))}
      </div>

      <div className="card">
        <h2>What the chain is actually for</h2>
        <p className="lede" style={{ marginBottom: 12 }}>
          Two different jobs, and conflating them is how this goes wrong.
        </p>
        <p style={{ marginTop: 0 }}>
          <strong>DKIM proves the bytes came from the institution.</strong> That is
          cryptography, and it needs no chain at all. But a DKIM selector gets retired
          eventually — normal key hygiene — and when the key leaves DNS, every signature
          under it becomes unverifiable to anyone who did not write the key down. So we
          capture the DNS record at first verification and commit its hash. That is what
          keeps a signature checkable in five years.
        </p>
        <p>
          <strong>The chain proves nothing was added later.</strong> Anchoring does not
          stop a lie; it stops a <em>later</em> lie. Every ingest gets a sequence number,
          so a manager who quietly drops a bad month leaves a gap anyone can read. At 0.3
          second blocks we anchor per ingest rather than nightly — and the difference
          matters, because a nightly batch proves the day rather than the moment, and the
          moment is the property worth having.
        </p>
      </div>

      {(records.data?.length ?? 0) > 0 && (
        <div className="card">
          <h3>All records on this instance</h3>
          <table>
            <thead>
              <tr>
                <th>Record</th>
                <th>Strategy</th>
                <th>Anchors</th>
              </tr>
            </thead>
            <tbody>
              {records.data?.map((record) => (
                <tr key={record.slug}>
                  <td>{record.name}</td>
                  <td className="muted">{record.strategy}</td>
                  <td className="mono small">
                    <a href={`/api/records/${record.slug}/anchors`}>timeline</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="small muted">
        Chain {config.data?.chain_id} ·{" "}
        {config.data?.registry_address ? (
          <a href={`${config.data.explorer_url}/address/${config.data.registry_address}`}>
            {config.data.registry_address}
          </a>
        ) : (
          "no registry configured — roots are computed but not anchored"
        )}
      </p>
    </div>
  );
}

function NdaGate({ view, token }: { view: RecordView; token: string }) {
  const queryClient = useQueryClient();
  const accept = useMutation({
    mutationFn: () => api.acceptNda(token),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["view", token] }),
  });

  return (
    <div className="shell">
      <Masthead />
      <div className="card" style={{ maxWidth: 620, margin: "48px auto" }}>
        <h2>{view.record.name}</h2>
        <p className="lede">
          Invited as <span className="mono">{view.viewer_email}</span> · disclosure
          profile <span className="mono">{view.profile}</span>
        </p>
        <p>{view.nda?.text}</p>
        <p className="small muted">
          Nothing behind this gate has been sent to your browser yet. Consent is written
          to an append-only log and committed on-chain before the first byte of data is
          served — which is why this page has no numbers on it to peek at.
        </p>
        <button onClick={() => accept.mutate()} disabled={accept.isPending}>
          {accept.isPending ? "Recording…" : `Accept and continue`}
        </button>
        {accept.isError && (
          <p className="small" style={{ color: "var(--tier-self_reported)" }}>
            {String(accept.error)}
          </p>
        )}
      </div>
    </div>
  );
}

function View({ token }: { token: string }) {
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const view = useQuery({ queryKey: ["view", token], queryFn: () => api.view(token) });

  useTitle(view.data ? `${view.data.record.name} — Pod Arena` : "Pod Arena");

  if (view.isLoading) return <div className="shell">Loading…</div>;
  if (view.isError)
    return (
      <div className="shell">
        <Masthead />
        <div className="card">
          <h2>That link does not open anything</h2>
          <p className="muted small">{String(view.error)}</p>
          <p className="small">
            Invites are bound to one identity, expire, and can be revoked. That is the
            point of them.
          </p>
        </div>
      </div>
    );

  const data = view.data!;
  if (data.state === "nda_required") return <NdaGate view={data} token={token} />;

  const anchors = data.anchor;

  return (
    <div className="shell">
      {data.watermark && <Watermark viewer={data.watermark.viewer} at={data.watermark.at} />}
      <Masthead />
      {config.data?.demo_fixtures && <DemoBanner />}

      <div className="row spread" style={{ marginBottom: 6 }}>
        <h1>{data.record.name}</h1>
        <TierBadge tier={data.tier} label={data.tier_label} />
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        {data.record.strategy} · {data.tier_meaning}
      </p>

      <div className="card">
        <h2>Net of fees</h2>
        <p className="lede">
          What the investor actually received. The tier under each number is the weakest
          piece of evidence that fed it — one self-reported row caps the whole metric.
        </p>
        <MetricGrid metrics={data.metrics} basis="net" />
      </div>

      {data.metrics.some((m) => m.basis === "gross") && (
        <div className="card">
          <h2>Gross</h2>
          <p className="lede">
            Fees added back, from terms the manager states rather than anything a broker
            signed. Shown beside net because presenting one without the other is how
            performance advertising goes wrong.
          </p>
          <MetricGrid metrics={data.metrics} basis="gross" />
        </div>
      )}

      {data.nav_series && data.nav_series.length > 1 && (
        <div className="card">
          <h2>Net asset value</h2>
          <p className="lede">
            {data.nav_series.length} observations ·{" "}
            {money(data.nav_series[data.nav_series.length - 1].amount_minor, data.nav_series[0].currency)}{" "}
            at the last one
          </p>
          <NavChart series={data.nav_series} flows={data.flows} />
        </div>
      )}

      {config.data && (
        <VerifyPanel
          view={data}
          token={token}
          chainId={config.data.chain_id}
          defaultRpc={config.data.rpc_url}
          registry={config.data.registry_address}
          chainKey={data.record.chain_key ?? null}
        />
      )}

      {data.findings && data.findings.length > 0 && (
        <div className="card">
          <h2>What we could not reconcile</h2>
          <p className="lede">
            Written down rather than hidden. An allocator cares more about the
            discrepancies we surface than the ones we do not.
          </p>
          {data.findings.map((finding, index) => (
            <div className={`finding ${finding.severity}`} key={index}>
              <div className="kind">
                {finding.kind} · {finding.severity}
                {finding.as_of ? ` · ${finding.as_of}` : ""}
              </div>
              <div>{finding.detail}</div>
            </div>
          ))}
        </div>
      )}

      {data.evidence && (
        <div className="card">
          <h2>Evidence</h2>
          <p className="lede">
            The documents themselves, each with the institution's signature and the DNS
            key exactly as it stood when we first checked it.
          </p>
          <EvidenceTable evidence={data.evidence} token={token} />
        </div>
      )}

      {data.positions && data.positions.length > 0 && (
        <div className="card">
          <h2>Positions</h2>
          <p className="lede">
            Opt-in, per viewer, every time. Most viewers never see this section.
          </p>
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Instrument</th>
                <th className="num">Quantity</th>
                <th className="num">Price</th>
                <th className="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {data.positions.map((position, index) => (
                <tr key={index}>
                  <td>{position.as_of}</td>
                  <td>{position.instrument}</td>
                  <td className="num">{position.quantity}</td>
                  <td className="num">{position.price}</td>
                  <td className="num">
                    {position.amount_minor !== null
                      ? money(position.amount_minor, position.currency)
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card">
        <h3>Snapshot {data.snapshot.seq}</h3>
        <table>
          <tbody>
            <tr>
              <td className="muted">Merkle root</td>
              <td className="mono">{data.snapshot.root}</td>
            </tr>
            <tr>
              <td className="muted">Methodology</td>
              <td className="mono">{data.snapshot.methodology_version}</td>
            </tr>
            <tr>
              <td className="muted">Extractors</td>
              <td className="mono">
                {Object.entries(data.snapshot.extractor_versions)
                  .map(([id, version]) => `${id} v${version}`)
                  .join(" · ")}
              </td>
            </tr>
            <tr>
              <td className="muted">Anchor</td>
              <td className="mono">
                {anchors?.tx_hash ? (
                  <a href={`${config.data?.explorer_url}/tx/${anchors.tx_hash}`}>
                    {anchors.tx_hash.slice(0, 18)}… (block {anchors.block_number})
                  </a>
                ) : (
                  (anchors?.error ?? "not anchored")
                )}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function App() {
  const current = route();
  if (current.name === "view") return <View token={current.token} />;
  return <Home />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
