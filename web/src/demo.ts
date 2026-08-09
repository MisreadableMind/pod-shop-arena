/** The staged demo, in one place.
 *
 *  The seeder mints these invite tokens deterministically (demo/seed.py), so
 *  the links survive a reseed and a redeploy. Real invites get 32 bytes from
 *  `secrets.token_urlsafe` and only their hash is ever stored — see the note in
 *  `_invite()` on why the fixtures are allowed to be an exception. */

export type DemoInvite = {
  token: string;
  record: string;
  viewer: string;
  profile: string;
  blurb: string;
};

export const DEMO_INVITES: DemoInvite[] = [
  {
    token: "demo-meridian-full",
    record: "Meridian Global Macro",
    viewer: "allocator@example-endowment.org",
    profile: "full_detail",
    blurb: "Twelve months, every one signed by the broker's own key. This is what good looks like.",
  },
  {
    token: "demo-northwind-full",
    record: "Northwind Partners",
    viewer: "allocator@example-endowment.org",
    profile: "full_detail",
    blurb:
      "The same twelve numbers, with one month typed into a spreadsheet. Watch what it costs.",
  },
  {
    token: "demo-evidence-lab",
    record: "Evidence Lab",
    viewer: "allocator@example-endowment.org",
    profile: "full_detail",
    blurb:
      "Five ways a signature fails: a retired key, an l= tag, one flipped byte, a hand-forward, a stranger.",
  },
  {
    token: "demo-meridian-summary",
    record: "Meridian Global Macro",
    viewer: "cautious@example-fund.com",
    profile: "summary",
    blurb:
      "The same fund as the first link, through the narrowest window. Open both and compare.",
  },
];

export const PROFILE_LABELS: Record<string, string> = {
  summary: "Summary",
  ratios_and_risk: "Ratios & risk",
  full_detail: "Full detail",
  full_plus_positions: "Full + positions",
};

export const PROFILE_MEANING: Record<string, string> = {
  summary: "Headline return only. No risk ratios, no evidence, no chart.",
  ratios_and_risk: "Adds volatility, Sharpe, Sortino, Calmar, drawdown, VaR.",
  full_detail: "Adds the evidence, the findings, the NAV series and the Merkle leaves.",
  full_plus_positions: "Adds positions, instrument by instrument. The rung managers lose sleep over.",
};

export function kb(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} kB`;
}
