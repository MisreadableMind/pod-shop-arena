export type Tier =
  | "source_signed"
  | "aggregator_attested"
  | "platform_observed"
  | "self_reported";

export type Metric = {
  key: string;
  basis: "net" | "gross";
  value: string;
  unit: string;
  formula: string;
  tier: Tier;
  inputs: Record<string, unknown>;
};

export type DkimInfo = {
  verified: boolean;
  d_domain: string | null;
  selector: string | null;
  algo: string | null;
  l_tag_present: boolean;
  body_hash_matched: boolean;
  dns_txt_record: string | null;
  dns_captured_at: string | null;
  failure_reason: string | null;
  signatures: Array<{
    index: number;
    domain: string | null;
    considered: boolean;
    verified: boolean;
    reason: string | null;
  }>;
};

export type Evidence = {
  sha256: string;
  filename: string | null;
  doc_type: string;
  channel: string;
  institution_id: string | null;
  byte_length: number;
  received_at: string;
  dkim?: DkimInfo;
};

export type Leaf = { kind: string; ref: string; digest: string; label: string };

export type RecordView = {
  state: "open" | "nda_required";
  record: {
    slug: string;
    name: string;
    strategy?: string | null;
    chain_key?: string;
  };
  profile: string;
  viewer_email?: string;
  nda?: { version: string; text: string };
  tier: Tier;
  tier_label: string;
  tier_meaning: string;
  snapshot: {
    seq: number;
    root: string;
    metrics_hash: string;
    methodology_version: string;
    extractor_versions: Record<string, string>;
    created_at: string;
  };
  anchor: {
    status: string;
    chain_id: number;
    root: string;
    seq: number;
    tx_hash: string | null;
    block_number: number | null;
    confirmed_at: string | null;
    error: string | null;
  } | null;
  metrics: Metric[];
  findings?: Array<{
    kind: string;
    severity: string;
    detail: string;
    as_of: string | null;
  }>;
  evidence?: Evidence[];
  nav_series?: Array<{
    as_of: string;
    amount_minor: number;
    currency: string;
    tier: Tier;
  }>;
  flows?: Array<{
    as_of: string;
    amount_minor: number;
    currency: string;
    tier: Tier;
    note: string | null;
  }>;
  merkle_leaves?: Leaf[];
  positions?: Array<{
    as_of: string;
    kind: string;
    instrument: string | null;
    quantity: string | null;
    price: string | null;
    amount_minor: number | null;
    currency: string;
    tier: Tier;
  }>;
  watermark?: { viewer: string; at: string; record: string };
};

export type AppConfig = {
  chain_id: number;
  rpc_url: string;
  explorer_url: string;
  registry_address: string | null;
  anchoring_enabled: boolean;
  demo_fixtures: boolean;
  methodology_version: string;
  /** Null unless this instance runs the synthetic corpus. */
  demo_admin_token: string | null;
};

export const PROFILES = [
  "summary",
  "ratios_and_risk",
  "full_detail",
  "full_plus_positions",
] as const;

export type ProfileSlug = (typeof PROFILES)[number];

export type DisclosureRung = {
  profile: ProfileSlug;
  rank: number;
  bytes: number;
  keys: string[];
  metric_keys: string[];
  counts: {
    metrics: number;
    evidence: number;
    findings: number;
    nav_series: number;
    positions: number;
    merkle_leaves: number;
  };
};

export type DisclosureMatrix = {
  record: { slug: string; name: string };
  profiles: DisclosureRung[];
  sections: string[];
};

export type InviteRow = {
  id: string;
  viewer_email: string;
  profile: ProfileSlug;
  status: "active" | "revoked" | "expired";
  nda_accepted_at: string | null;
  expires_at: string;
  created_at: string;
  views: number;
  last_seen_at: string | null;
};

export type AccessRow = {
  at: string;
  action: string;
  viewer_email: string;
  profile: string;
  ip: string | null;
  chain_tx: string | null;
  explorer_url: string | null;
};

export type NewInvite = {
  token: string;
  profile: string;
  viewer_email: string;
  expires_at: string;
  url: string;
};

export type RebuildResult = {
  seq: number;
  root: string;
  tier: Tier;
  metrics: number;
  findings: number;
  anchor_status: string;
  tx_hash: string | null;
  explorer_url: string | null;
};

export type AnchorTimeline = {
  record: { slug: string; name: string };
  chain_key: string;
  chain_id: number;
  registry_address: string | null;
  snapshots: Array<{
    seq: number;
    root: string;
    tier: Tier;
    created_at: string;
    leaf_count: number;
    anchor: {
      status: string;
      tx_hash: string | null;
      block_number: number | null;
      explorer_url: string | null;
    } | null;
  }>;
};

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status}: ${body.slice(0, 240)}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  config: () => fetch("/api/config").then(json<AppConfig>),
  records: () =>
    fetch("/api/records").then(
      json<Array<{ slug: string; name: string; strategy: string | null }>>,
    ),
  view: (token: string) => fetch(`/api/view/${token}`).then(json<RecordView>),
  acceptNda: (token: string) =>
    fetch(`/api/view/${token}/nda`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ accept: true }),
    }).then(json<{ state: string; chain_tx: string | null }>),
  proof: (token: string, digest: string) =>
    fetch(`/api/view/${token}/proof/${digest}`).then(
      json<{ root: string; leaf: string; steps: Array<{ sibling: string; side: "left" | "right" }> }>,
    ),
  anchors: (slug: string) =>
    fetch(`/api/records/${slug}/anchors`).then(json<AnchorTimeline>),
  bundleUrl: (token: string) => `/api/view/${token}/bundle`,
  documentUrl: (token: string, sha: string) => `/api/view/${token}/document/${sha}`,
};

// -- the manager's side ----------------------------------------------------
//
// Everything below needs the admin bearer token. It is held in localStorage
// rather than a cookie on purpose: no cookie means no ambient authority, so a
// link an allocator clicks can never carry the manager's credentials with it.

const TOKEN_KEY = "podarena.admin";

export const adminToken = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

async function authed<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = adminToken.get();
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init.headers ?? {}),
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
  });
  if (response.status === 401 || response.status === 503) {
    throw new Error("unauthorized");
  }
  return json<T>(response);
}

export const owner = {
  view: (slug: string) => authed<RecordView>(`/api/records/${slug}/owner`),
  disclosure: (slug: string) => authed<DisclosureMatrix>(`/api/records/${slug}/disclosure`),
  preview: (slug: string, profile: ProfileSlug) =>
    authed<RecordView>(`/api/records/${slug}/preview/${profile}`),
  invites: (slug: string) => authed<InviteRow[]>(`/api/records/${slug}/invites`),
  accessLog: (slug: string) => authed<AccessRow[]>(`/api/records/${slug}/access-log`),
  createInvite: (slug: string, body: { viewer_email: string; profile: string }) =>
    authed<NewInvite>(`/api/records/${slug}/invites`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }),
  revokeInvite: (id: string) =>
    authed<{ id: string; revoked_at: string }>(`/api/invites/${id}/revoke`, {
      method: "POST",
    }),
  rebuild: (slug: string) =>
    authed<RebuildResult>(`/api/records/${slug}/rebuild`, { method: "POST" }),
};
