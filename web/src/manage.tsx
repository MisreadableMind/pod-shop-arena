import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  PROFILES,
  adminToken,
  api,
  owner,
  type DisclosureMatrix,
  type InviteRow,
  type ProfileSlug,
  type RecordView,
} from "./api";
import { EvidenceTable, MetricGrid, NavChart, TierBadge, useTitle } from "./components";
import { DEMO_INVITES, PROFILE_LABELS, PROFILE_MEANING, kb } from "./demo";
import { Page } from "./shell";

// -- login ----------------------------------------------------------------

/** The console's door.
 *
 *  On a fixtures instance the token is handed over by /api/config and typed
 *  into the box for you — three minutes of demo should not be three minutes of
 *  typing. On an instance holding real evidence that field is null and the box
 *  is empty, because `demo_fixtures` and real evidence cannot both be true. */
function LoginGate({ onAuthed }: { onAuthed: () => void }) {
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const demoToken = config.data?.demo_admin_token ?? "";
  const [value, setValue] = useState("");

  const submit = (token: string) => {
    if (!token.trim()) return;
    adminToken.set(token.trim());
    onAuthed();
  };

  return (
    <Page>
      <div className="card card-accent" style={{ maxWidth: 560, margin: "40px auto" }}>
        <h2>Manager console</h2>
        <p className="lede">
          This is the manager's side. You see all of it. And every time the console shows
          you something an allocator hasn't been granted, it says so.
        </p>
        <div className="row">
          <input
            type="text"
            value={value}
            placeholder="admin token"
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && submit(value)}
            aria-label="Admin token"
          />
          <button onClick={() => submit(value)} disabled={!value.trim()}>
            Sign in
          </button>
        </div>

        {demoToken && (
          <div className="creds" style={{ marginTop: 18 }}>
            <div className="card-head" style={{ marginBottom: 8 }}>
              <h3>Demo credentials</h3>
              <span className="pill">fixtures instance</span>
            </div>
            <div className="hashline">
              <span className="k">Manager token</span>
              <span className="v">{demoToken}</span>
            </div>
            <button className="ghost" style={{ marginTop: 14 }} onClick={() => submit(demoToken)}>
              Use the demo token
            </button>
          </div>
        )}
      </div>
    </Page>
  );
}

/** Reads the stored token once into state, so signing in or out re-renders the
 *  console without a page reload. */
function useAdminGate(): { authed: boolean; signIn: () => void; signOut: () => void } {
  const [token, setToken] = useState<string | null>(() => adminToken.get());
  return {
    authed: !!token,
    signIn: () => setToken(adminToken.get()),
    signOut: () => {
      adminToken.clear();
      setToken(null);
    },
  };
}

// -- fund list ------------------------------------------------------------

export function ManageHome() {
  useTitle("Manager console — PodShop Arena");
  const gate = useAdminGate();
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const records = useQuery({ queryKey: ["records"], queryFn: api.records });

  if (!gate.authed) return <LoginGate onAuthed={gate.signIn} />;

  return (
    <Page mode="owner">
      <div className="record-head">
        <div className="row spread">
          <h1>Your funds</h1>
          <button className="ghost" onClick={gate.signOut}>
            Sign out
          </button>
        </div>
        <p className="muted">
          Everything this instance holds, and every key you've handed out against it.
        </p>
      </div>

      <div className="card">
        <div className="card-head">
          <h2>Records</h2>
          <span className="pill">{records.data?.length ?? 0} funds</span>
        </div>
        {records.data?.map((record) => (
          <a className="record-link" key={record.slug} href={`/manage/${record.slug}`}>
            <div>
              <div className="name">{record.name}</div>
              <div className="small muted">{record.strategy}</div>
            </div>
            <span className="arrow" aria-hidden>
              →
            </span>
          </a>
        ))}
      </div>

      {config.data?.demo_fixtures && (
        <div className="card">
          <div className="card-head">
            <h2>Demo credentials</h2>
            <span className="pill">synthetic corpus</span>
          </div>
          <p className="lede">
            Two sides, two kinds of credential. You sign in with a token. An allocator
            never gets an account at all — just one link, tied to their address and to a
            profile, and you can take it back.
          </p>

          <h3 style={{ marginTop: 20 }}>Manager</h3>
          <div className="hashline">
            <span className="k">Console</span>
            <span className="v">
              <a href="/manage">/manage</a>
            </span>
          </div>
          <div className="hashline">
            <span className="k">Token</span>
            <span className="v">{config.data.demo_admin_token ?? "open instance"}</span>
          </div>

          <h3 style={{ marginTop: 24 }}>Allocators</h3>
          <table>
            <thead>
              <tr>
                <th>Invited address</th>
                <th>Record</th>
                <th>Profile</th>
                <th>Link</th>
              </tr>
            </thead>
            <tbody>
              {DEMO_INVITES.map((invite) => (
                <tr key={invite.token}>
                  <td className="mono small">{invite.viewer}</td>
                  <td>{invite.record}</td>
                  <td>
                    <span className="pill">{PROFILE_LABELS[invite.profile]}</span>
                  </td>
                  <td className="small">
                    <a href={`/view/${invite.token}`}>open</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Page>
  );
}

// -- one fund -------------------------------------------------------------

export function ManageRecord({ slug }: { slug: string }) {
  const gate = useAdminGate();
  const queryClient = useQueryClient();
  const [profile, setProfile] = useState<ProfileSlug>("summary");

  const view = useQuery({
    queryKey: ["owner", slug],
    queryFn: () => owner.view(slug),
    enabled: gate.authed,
  });
  const matrix = useQuery({
    queryKey: ["disclosure", slug],
    queryFn: () => owner.disclosure(slug),
    enabled: gate.authed,
  });
  const preview = useQuery({
    queryKey: ["preview", slug, profile],
    queryFn: () => owner.preview(slug, profile),
    enabled: gate.authed,
  });
  const invites = useQuery({
    queryKey: ["invites", slug],
    queryFn: () => owner.invites(slug),
    enabled: gate.authed,
  });
  const access = useQuery({
    queryKey: ["access", slug],
    queryFn: () => owner.accessLog(slug),
    enabled: gate.authed,
  });
  const anchors = useQuery({
    queryKey: ["anchors", slug],
    queryFn: () => api.anchors(slug),
    enabled: gate.authed,
  });

  useTitle(view.data ? `${view.data.record.name} — console` : "Manager console");

  const rebuild = useMutation({
    mutationFn: () => owner.rebuild(slug),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["owner", slug] });
      queryClient.invalidateQueries({ queryKey: ["anchors", slug] });
      queryClient.invalidateQueries({ queryKey: ["disclosure", slug] });
    },
  });

  if (!gate.authed) return <LoginGate onAuthed={gate.signIn} />;
  if (view.isError && String(view.error).includes("unauthorized"))
    return <LoginGate onAuthed={gate.signIn} />;
  if (view.isLoading)
    return (
      <Page mode="owner">
        <p className="muted">Loading…</p>
      </Page>
    );
  if (view.isError)
    return (
      <Page mode="owner">
        <div className="card">
          <h2>Could not open {slug}</h2>
          <p className="muted small">{String(view.error)}</p>
        </div>
      </Page>
    );

  const data = view.data!;

  return (
    <Page mode="owner">
      <div className="record-head">
        <div className="row spread">
          <h1>{data.record.name}</h1>
          <div className="row">
            <TierBadge tier={data.tier} label={data.tier_label} />
            <button onClick={() => rebuild.mutate()} disabled={rebuild.isPending}>
              {rebuild.isPending ? "Re-anchoring…" : "Rebuild & re-anchor"}
            </button>
          </div>
        </div>
        <p className="muted">
          {data.record.strategy} · snapshot {data.snapshot.seq} ·{" "}
          <span className="mono">{data.snapshot.root.slice(0, 22)}…</span>
        </p>
        {rebuild.isSuccess && (
          <p className="small" style={{ marginTop: 10 }}>
            Snapshot {rebuild.data.seq} built — {rebuild.data.metrics} metrics,{" "}
            {rebuild.data.findings} findings, anchor {rebuild.data.anchor_status}
            {rebuild.data.explorer_url && (
              <>
                {" · "}
                <a href={rebuild.data.explorer_url}>transaction</a>
              </>
            )}
          </p>
        )}
        {rebuild.isError && (
          <p className="small" style={{ marginTop: 10, color: "var(--color-umber)" }}>
            {String(rebuild.error)}
          </p>
        )}
      </div>

      <DisclosurePanel
        matrix={matrix.data}
        profile={profile}
        onProfile={setProfile}
        ownerBytes={
          matrix.data?.profiles[matrix.data.profiles.length - 1]?.bytes ?? 0
        }
      />

      <AllocatorPreview
        profile={profile}
        preview={preview.data}
        loading={preview.isLoading}
        matrix={matrix.data}
      />

      <div className="card">
        <div className="card-head">
          <h2>What you see</h2>
          <span className="pill">nothing withheld</span>
        </div>
        <p className="lede">
          Every metric the engine produced, on every basis. This is as wide as it goes.
          It's the same function that builds an allocator's response, just run with the
          ceiling taken off.
        </p>
        <MetricGrid metrics={data.metrics} basis="net" />
        {data.metrics.some((metric) => metric.basis === "gross") && (
          <>
            <h3 style={{ marginTop: 22, marginBottom: 12 }}>Gross</h3>
            <MetricGrid metrics={data.metrics} basis="gross" />
          </>
        )}
        {data.nav_series && data.nav_series.length > 1 && (
          <div style={{ marginTop: 24 }}>
            <NavChart series={data.nav_series} flows={data.flows} />
          </div>
        )}
      </div>

      <InvitePanel slug={slug} invites={invites.data} />

      <div className="card">
        <div className="card-head">
          <h2>Who opened it</h2>
          <span className="pill">{access.data?.length ?? 0} events</span>
        </div>
        <p className="lede">
          Append-only, and each row goes on-chain as it's written. You can't quietly delete
          a view here. Neither can we.
        </p>
        {(access.data?.length ?? 0) === 0 ? (
          <p className="muted small">Nobody has opened this one yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>Action</th>
                <th>Profile</th>
                <th>On-chain</th>
              </tr>
            </thead>
            <tbody>
              {access.data?.map((event, index) => (
                <tr key={index}>
                  <td className="mono small">{event.at.slice(0, 19).replace("T", " ")}</td>
                  <td className="small">{event.viewer_email}</td>
                  <td className="small">{event.action}</td>
                  <td className="small">
                    <span className="pill">
                      {PROFILE_LABELS[event.profile] ?? event.profile}
                    </span>
                  </td>
                  <td className="mono small">
                    {event.explorer_url ? (
                      <a href={event.explorer_url}>{event.chain_tx?.slice(0, 14)}…</a>
                    ) : (
                      <span className="muted">not anchored</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <div className="card-head">
          <h2>Anchor timeline</h2>
          <span className="pill">{anchors.data?.snapshots.length ?? 0} snapshots</span>
        </div>
        <p className="lede">
          Public on purpose. Every ingest gets a number, so a month you quietly drop leaves
          a gap an allocator can count without having to ask you about it.
        </p>
        <table>
          <thead>
            <tr>
              <th className="num">Seq</th>
              <th>Root</th>
              <th>Tier</th>
              <th className="num">Leaves</th>
              <th>Anchor</th>
            </tr>
          </thead>
          <tbody>
            {anchors.data?.snapshots.map((snapshot) => (
              <tr key={snapshot.seq}>
                <td className="num">{snapshot.seq}</td>
                <td className="mono small">{snapshot.root.slice(0, 20)}…</td>
                <td>
                  <TierBadge tier={snapshot.tier} />
                </td>
                <td className="num">{snapshot.leaf_count}</td>
                <td className="mono small">
                  {snapshot.anchor?.explorer_url ? (
                    <a href={snapshot.anchor.explorer_url}>
                      {snapshot.anchor.tx_hash?.slice(0, 14)}…
                    </a>
                  ) : (
                    <span className="muted">{snapshot.anchor?.status ?? "none"}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Page>
  );
}

// -- the disclosure fence, made visible ------------------------------------

const SECTION_LABELS: Record<string, string> = {
  metrics: "Metrics",
  findings: "Reconciliation findings",
  evidence: "Evidence documents",
  nav_series: "NAV series",
  flows: "Cash flows",
  merkle_leaves: "Merkle leaves",
  positions: "Positions",
  snapshot: "Snapshot header",
  anchor: "Anchor",
  record: "Record identity",
  tier: "Tier",
  tier_label: "Tier label",
  tier_meaning: "Tier meaning",
  profile: "Profile",
};

/** The panel this whole console exists for.
 *
 *  A manager's question is never "is it hidden in the UI" — it is "did it leave
 *  the building". So each rung here is the projection actually run, and the
 *  number in the column is the serialized size of what would go on the wire. A
 *  dash means the key is absent from the JSON, not styled out of the page. */
function DisclosurePanel({
  matrix,
  profile,
  onProfile,
  ownerBytes,
}: {
  matrix?: DisclosureMatrix;
  profile: ProfileSlug;
  onProfile: (profile: ProfileSlug) => void;
  ownerBytes: number;
}) {
  if (!matrix) return null;

  const varying = matrix.sections.filter((section) => {
    const present = matrix.profiles.map((rung) => rung.keys.includes(section));
    return present.some(Boolean) && !present.every(Boolean);
  });
  const always = matrix.sections.filter((section) =>
    matrix.profiles.every((rung) => rung.keys.includes(section)),
  );

  return (
    <div className="card card-accent">
      <div className="card-head">
        <h2>What each allocator can see</h2>
        <span className="pill">measured, not asserted</span>
      </div>
      <p className="lede">
        One row per section, one column per profile. A dash doesn't mean hidden. It means
        the key isn't in the response at all. Click a column and we'll render that exact
        payload below.
      </p>

      <div className="matrix-wrap">
        <table className="matrix">
          <thead>
            <tr>
              <th>Section</th>
              {matrix.profiles.map((rung) => (
                <th
                  key={rung.profile}
                  className={`matrix-col ${rung.profile === profile ? "on" : ""}`}
                  onClick={() => onProfile(rung.profile)}
                >
                  {PROFILE_LABELS[rung.profile] ?? rung.profile}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="matrix-bytes">
              <td>Bytes on the wire</td>
              {matrix.profiles.map((rung) => (
                <td
                  key={rung.profile}
                  className={`num matrix-col ${rung.profile === profile ? "on" : ""}`}
                  onClick={() => onProfile(rung.profile)}
                >
                  {kb(rung.bytes)}
                </td>
              ))}
            </tr>
            {varying.map((section) => (
              <tr key={section}>
                <td>{SECTION_LABELS[section] ?? section}</td>
                {matrix.profiles.map((rung) => {
                  const present = rung.keys.includes(section);
                  const count =
                    rung.counts[section as keyof typeof rung.counts] ?? undefined;
                  return (
                    <td
                      key={rung.profile}
                      className={`num matrix-col ${rung.profile === profile ? "on" : ""}`}
                      onClick={() => onProfile(rung.profile)}
                    >
                      {present ? (
                        <span className="cell-yes">{count ?? "✓"}</span>
                      ) : (
                        <span className="cell-no">—</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr>
              <td>Metrics</td>
              {matrix.profiles.map((rung) => (
                <td
                  key={rung.profile}
                  className={`num matrix-col ${rung.profile === profile ? "on" : ""}`}
                  onClick={() => onProfile(rung.profile)}
                >
                  <span className="cell-yes">{rung.counts.metrics}</span>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <p className="small muted" style={{ marginTop: 14 }}>
        {always.length} sections travel at every profile:{" "}
        {always.map((section) => SECTION_LABELS[section] ?? section).join(", ")}. That's
        identity and provenance. Strip those out and there's nothing left to check.
      </p>
      <p className="small muted" style={{ marginTop: 6 }}>
        You're looking at {kb(ownerBytes)}. Your narrowest allocator gets{" "}
        {kb(matrix.profiles[0]?.bytes ?? 0)} of it.
      </p>
    </div>
  );
}

/** The same payload the allocator's browser would receive, rendered with the
 *  same components their page uses. Not a mock-up — one fetch against the real
 *  projection, so this and the allocator's screen cannot drift. */
function AllocatorPreview({
  profile,
  preview,
  loading,
  matrix,
}: {
  profile: ProfileSlug;
  preview?: RecordView;
  loading: boolean;
  matrix?: DisclosureMatrix;
}) {
  const rung = matrix?.profiles.find((row) => row.profile === profile);
  const absent = (matrix?.sections ?? []).filter(
    (section) => rung && !rung.keys.includes(section),
  );

  return (
    <div className="card preview-card">
      <div className="card-head">
        <h2>Previewing as an allocator</h2>
        <span className="pill pill-on">{PROFILE_LABELS[profile]}</span>
      </div>
      <p className="lede">{PROFILE_MEANING[profile]}</p>

      {loading && <p className="muted small">Rendering the allocator's payload…</p>}

      {preview && (
        <>
          <div className="preview-frame">
            <div className="preview-bar">
              <span className="mono small">/view/… · {PROFILE_LABELS[profile]}</span>
              <span className="mono small">{kb(rung?.bytes ?? 0)}</span>
            </div>
            <div className="preview-body">
              <MetricGrid metrics={preview.metrics} basis="net" />

              {preview.nav_series && preview.nav_series.length > 1 && (
                <div style={{ marginTop: 22 }}>
                  <h3 style={{ marginBottom: 10 }}>Net asset value</h3>
                  <NavChart series={preview.nav_series} flows={preview.flows} />
                </div>
              )}

              {preview.evidence && preview.evidence.length > 0 && (
                <div style={{ marginTop: 22 }}>
                  <h3 style={{ marginBottom: 10 }}>Evidence</h3>
                  <EvidenceTable evidence={preview.evidence} token={null} />
                </div>
              )}

              {preview.positions && preview.positions.length > 0 && (
                <div style={{ marginTop: 22 }}>
                  <h3 style={{ marginBottom: 10 }}>Positions</h3>
                  <p className="small muted">
                    {preview.positions.length} rows, instrument by instrument. Think hard
                    before you grant this one.
                  </p>
                </div>
              )}
            </div>
          </div>

          {absent.length > 0 && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ marginBottom: 8 }}>Not in this response</h3>
              <div className="row" style={{ gap: 8 }}>
                {absent.map((section) => (
                  <span key={section} className="pill pill-absent">
                    {SECTION_LABELS[section] ?? section}
                  </span>
                ))}
              </div>
              <p className="small muted" style={{ marginTop: 10 }}>
                Missing from the JSON, not hidden by the page. Open dev tools on the
                allocator's browser and you'll find nothing, because there's nothing there.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// -- invites ---------------------------------------------------------------

function InvitePanel({ slug, invites }: { slug: string; invites?: InviteRow[] }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("allocator@example-endowment.org");
  const [profile, setProfile] = useState<ProfileSlug>("summary");
  const [copied, setCopied] = useState(false);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["invites", slug] });
    queryClient.invalidateQueries({ queryKey: ["access", slug] });
  };

  const create = useMutation({
    mutationFn: () => owner.createInvite(slug, { viewer_email: email, profile }),
    onSuccess: refresh,
  });
  const revoke = useMutation({
    mutationFn: (id: string) => owner.revokeInvite(id),
    onSuccess: refresh,
  });

  const copy = (url: string) => {
    navigator.clipboard?.writeText(url);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="card">
      <div className="card-head">
        <h2>Who holds a key</h2>
        <span className="pill">{invites?.length ?? 0} invites</span>
      </div>
      <p className="lede">
        An allocator never gets an account. They get one link, tied to their address and to
        a profile. It expires, and you can revoke it in the middle of a conversation. We
        only store the token's hash, so this list can't re-send a link even if you ask it
        to. Issue a new one.
      </p>

      <div className="invite-form">
        <input
          type="text"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          aria-label="Allocator email"
        />
        <select
          value={profile}
          onChange={(event) => setProfile(event.target.value as ProfileSlug)}
          aria-label="Disclosure profile"
        >
          {PROFILES.map((slug) => (
            <option key={slug} value={slug}>
              {PROFILE_LABELS[slug]}
            </option>
          ))}
        </select>
        <button onClick={() => create.mutate()} disabled={create.isPending}>
          {create.isPending ? "Issuing…" : "Issue invite"}
        </button>
      </div>

      {create.isSuccess && (
        <div className="invite-issued">
          <div className="hashline">
            <span className="k">Link — shown once</span>
            <span className="v">{create.data.url}</span>
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <button className="ghost" onClick={() => copy(create.data.url)}>
              {copied ? "Copied" : "Copy link"}
            </button>
            <a className="small" href={`/view/${create.data.token}`}>
              open it as the allocator →
            </a>
          </div>
        </div>
      )}
      {create.isError && (
        <p className="small" style={{ color: "var(--color-umber)" }}>
          {String(create.error)}
        </p>
      )}

      {(invites?.length ?? 0) > 0 && (
        <table style={{ marginTop: 20 }}>
          <thead>
            <tr>
              <th>Allocator</th>
              <th>Profile</th>
              <th>Status</th>
              <th>NDA</th>
              <th className="num">Views</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {invites?.map((invite) => (
              <tr key={invite.id}>
                <td className="small mono">{invite.viewer_email}</td>
                <td>
                  <span className="pill">
                    {PROFILE_LABELS[invite.profile] ?? invite.profile}
                  </span>
                </td>
                <td>
                  <span className={`status status-${invite.status}`}>{invite.status}</span>
                </td>
                <td className="small muted">
                  {invite.nda_accepted_at
                    ? invite.nda_accepted_at.slice(0, 10)
                    : "not accepted"}
                </td>
                <td className="num">{invite.views}</td>
                <td>
                  {invite.status === "active" && (
                    <button
                      className="ghost small-btn"
                      onClick={() => revoke.mutate(invite.id)}
                      disabled={revoke.isPending}
                    >
                      Revoke
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
