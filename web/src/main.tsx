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
import { DEMO_INVITES, PROFILE_LABELS, PROFILE_MEANING } from "./demo";
import { ManageHome, ManageRecord } from "./manage";
import { Page } from "./shell";
import "./styles.css";

const client = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

// Four routes and no library. A router that needs a code-generation step to
// serve these would be more machinery than the problem has.
type Route =
  | { name: "home" }
  | { name: "view"; token: string }
  | { name: "manage" }
  | { name: "manage-record"; slug: string };

function route(): Route {
  const path = window.location.pathname;
  const view = path.match(/^\/view\/([^/]+)/);
  if (view) return { name: "view", token: view[1] };
  const record = path.match(/^\/manage\/([^/]+)/);
  if (record) return { name: "manage-record", slug: record[1] };
  if (path.startsWith("/manage")) return { name: "manage" };
  return { name: "home" };
}

function Home() {
  useTitle("PodShop Arena");
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });

  const hero = (
    <section className="hero">
      <div className="hero-inner">
        <h1>Anyone can type a track record.</h1>
        <p className="hero-lede">
          That's the whole problem. A manager mails an allocator twelve good months in a
          PDF, and the allocator can't tell those numbers from twelve numbers invented on a
          Tuesday. Every fix on offer asks the bank to cooperate — an API, a feed, a signed
          letter. Banks don't cooperate. So we stopped asking. It turns out your bank
          already signs something for you every month without thinking about it: the
          statement email sitting in your inbox. That signature is DKIM. We work from that.
        </p>
      </div>
    </section>
  );

  return (
    <Page hero={hero}>

      {/* Three doors, and which one you came through decides what exists. */}
      <div className="three-doors">
        <a className="door door-fund" href="/manage">
          <div className="door-role">The fund</div>
          <div className="door-name">Every pod</div>
          <p className="small muted">
            The platform's seat. The whole roster, every key any pod has handed out, and
            the only seat that can take a new pod on.
          </p>
          <span className="arrow" aria-hidden>
            →
          </span>
        </a>
        <a className="door door-pm" href="/manage">
          <div className="door-role">The portfolio manager</div>
          <div className="door-name">One pod</div>
          <p className="small muted">
            Runs a single book. Sees their own record and their own allocators. The pod
            next door doesn't exist as far as this seat is concerned.
          </p>
          <span className="arrow" aria-hidden>
            →
          </span>
        </a>
        <a className="door door-allocator" href={`/view/${DEMO_INVITES[0].token}`}>
          <div className="door-role">The allocator</div>
          <div className="door-name">One link</div>
          <p className="small muted">
            Outside the wall. No account, no password — one link, tied to your address,
            stamped with your name, killable mid-conversation.
          </p>
          <span className="arrow" aria-hidden>
            →
          </span>
        </a>
      </div>

      <div className="card">
        <div className="card-head">
          <h2>Start here</h2>
          <span className="pill">pre-loaded</span>
        </div>
        <p className="lede">
          Four links, already loaded, because nobody wants to watch someone fill in a form.
          Each one is an allocator's view. The same fund looks different depending on which
          link you came in through.
        </p>
        {DEMO_INVITES.map((invite) => (
          <a className="record-link" key={invite.token} href={`/view/${invite.token}`}>
            <div>
              <div className="name">{invite.record}</div>
              <div className="small muted">{invite.blurb}</div>
            </div>
            <span className="pill">{PROFILE_LABELS[invite.profile]}</span>
          </a>
        ))}
      </div>

      <div className="card">
        <h2>What the chain is actually for</h2>
        <p className="lede" style={{ marginBottom: 12 }}>
          Two jobs. Mix them up and the whole thing sounds like nonsense.
        </p>
        <p style={{ marginTop: 0 }}>
          <strong>DKIM proves the bytes came from the bank.</strong> That's just
          cryptography, and it needs no chain at all. But keys get retired eventually —
          ordinary hygiene, nobody's fault — and the day a key leaves DNS, every signature
          made under it becomes uncheckable by anyone who didn't write the key down. So we
          write it down. We grab the DNS record the first time we verify and commit its
          hash. That's what keeps a signature checkable in five years.
        </p>
        <p>
          <strong>The chain proves nothing was added later.</strong> Anchoring doesn't stop
          a lie. It stops a <em>later</em> lie, which is the kind managers actually tell.
          Every ingest gets a number, so if you quietly drop a bad month you leave a gap
          anyone can count. Blocks land here in 0.3 seconds, so we anchor every ingest
          instead of batching overnight. A nightly batch proves the day. We wanted the
          moment.
        </p>
      </div>


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
    </Page>
  );
}

function NdaGate({ view, token }: { view: RecordView; token: string }) {
  const queryClient = useQueryClient();
  const accept = useMutation({
    mutationFn: () => api.acceptNda(token),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["view", token] }),
  });

  return (
    <Page>
      <div
        className="card card-accent"
        style={{ maxWidth: 620, margin: "40px auto", paddingTop: 30 }}
      >
        <h2>{view.record.name}</h2>
        <p className="lede">
          Invited as <span className="mono">{view.viewer_email}</span> · disclosure
          profile <span className="mono">{view.profile}</span>
        </p>
        <p>{view.nda?.text}</p>
        <p className="small muted">
          There are no numbers on this page to peek at, and that's deliberate. Nothing
          behind this gate has reached your browser yet. Your consent gets written to an
          append-only log and put on-chain first. Only then does the data move.
        </p>
        <button onClick={() => accept.mutate()} disabled={accept.isPending}>
          {accept.isPending ? "Recording…" : `Accept and continue`}
        </button>
        {accept.isError && (
          <p className="small" style={{ color: "var(--color-umber)", marginTop: 12 }}>
            {String(accept.error)}
          </p>
        )}
      </div>
    </Page>
  );
}

function View({ token }: { token: string }) {
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const view = useQuery({ queryKey: ["view", token], queryFn: () => api.view(token) });

  useTitle(view.data ? `${view.data.record.name} — PodShop Arena` : "PodShop Arena");

  if (view.isLoading)
    return (
      <Page>
        <p className="muted">Loading…</p>
      </Page>
    );
  if (view.isError)
    return (
      <Page>
        <div className="card" style={{ maxWidth: 620, margin: "40px auto" }}>
          <h2>This link doesn't open anything</h2>
          <p className="muted small">{String(view.error)}</p>
          <p className="small">
            Invites are tied to one person, they expire, and they can be revoked. That's
            what makes them worth handing out.
          </p>
        </div>
      </Page>
    );

  const data = view.data!;
  if (data.state === "nda_required") return <NdaGate view={data} token={token} />;

  const anchors = data.anchor;

  return (
    <Page>
      {data.watermark && <Watermark viewer={data.watermark.viewer} at={data.watermark.at} />}

      <div className="record-head">
        <div className="row spread">
          <h1>{data.record.name}</h1>
          <TierBadge tier={data.tier} label={data.tier_label} />
        </div>
        <p className="muted">
          {data.record.strategy} · {data.tier_meaning}
        </p>
      </div>

      {/* The allocator's half of the disclosure contract. Saying which window
          you are looking through is part of the evidence: a number withheld
          silently is indistinguishable from a number that does not exist. */}
      <div className="profile-strip">
        <div>
          <span className="k">Your disclosure profile</span>
          <span className="pill pill-on">
            {PROFILE_LABELS[data.profile] ?? data.profile}
          </span>
        </div>
        <p className="small muted">
          {PROFILE_MEANING[data.profile]} Anything above that rung was never built into
          this response in the first place. If you want more, ask {data.record.name}. We
          can't give it to you.
        </p>
      </div>

      <div className="card">
        <div className="card-head">
          <h2>Net of fees</h2>
          <span className="pill">what the investor received</span>
        </div>
        <p className="lede">
          The number that ends up in the investor's account, after everyone took their cut.
          Under each one is the weakest evidence that fed it. A single typed-in row drags
          the whole metric down to typed-in, and that's on purpose.
        </p>
        <MetricGrid metrics={data.metrics} basis="net" />
      </div>

      {data.metrics.some((m) => m.basis === "gross") && (
        <div className="card">
          <h2>Gross</h2>
          <p className="lede">
            The same numbers with the fees added back, using terms the manager states. No
            broker signed for these. We show them next to net because showing gross on its
            own is how performance advertising goes bad.
          </p>
          <MetricGrid metrics={data.metrics} basis="gross" />
        </div>
      )}

      {data.nav_series && data.nav_series.length > 1 && (
        <div className="card">
          <div className="card-head">
            <h2>Net asset value</h2>
            <span className="pill">{data.nav_series.length} observations</span>
          </div>
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
          <h2>What didn't add up</h2>
          <p className="lede">
            We write these down instead of hiding them. A page with no discrepancies on it
            isn't cleaner than this one. It's just quieter.
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
          <div className="card-head">
            <h2>Evidence</h2>
            <span className="pill">{data.evidence.length} documents</span>
          </div>
          <p className="lede">
            The actual documents. Each one carries the bank's signature and the DNS key
            exactly as it stood the first time we looked.
          </p>
          <EvidenceTable evidence={data.evidence} token={token} />
        </div>
      )}

      {data.positions && data.positions.length > 0 && (
        <div className="card">
          <h2>Positions</h2>
          <p className="lede">
            Opt-in, per viewer, every single time. Most people never see this section.
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
        <div className="card-head">
          <h3>Snapshot {data.snapshot.seq}</h3>
          <span className="pill">{data.snapshot.methodology_version}</span>
        </div>
        <div style={{ marginTop: 10 }}>
          <div className="hashline">
            <span className="k">Merkle root</span>
            <span className="v">{data.snapshot.root}</span>
          </div>
          <div className="hashline">
            <span className="k">Metrics hash</span>
            <span className="v">{data.snapshot.metrics_hash}</span>
          </div>
          <div className="hashline">
            <span className="k">Extractors</span>
            <span className="v">
              {Object.entries(data.snapshot.extractor_versions)
                .map(([id, version]) => `${id} v${version}`)
                .join(" · ")}
            </span>
          </div>
          <div className="hashline">
            <span className="k">Anchor</span>
            <span className="v">
              {anchors?.tx_hash ? (
                <a href={`${config.data?.explorer_url}/tx/${anchors.tx_hash}`}>
                  {anchors.tx_hash.slice(0, 18)}… (block {anchors.block_number})
                </a>
              ) : (
                (anchors?.error ?? "not anchored")
              )}
            </span>
          </div>
        </div>
      </div>
    </Page>
  );
}

function App() {
  const current = route();
  if (current.name === "view") return <View token={current.token} />;
  if (current.name === "manage-record") return <ManageRecord slug={current.slug} />;
  if (current.name === "manage") return <ManageHome />;
  return <Home />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
