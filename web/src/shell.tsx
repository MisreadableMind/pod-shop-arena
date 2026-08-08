import type { ReactNode } from "react";

/** Which seat you're in. Three of them, and the whole product is the wall
 *  between them:
 *
 *  - `fund`  — the platform. Sees every pod on the roster.
 *  - `pm`    — one pod. Sees their own record and nothing next door.
 *  - (none)  — the allocator, or the public site. One link, no account.
 */
export type Seat = "fund" | "pm";

const SEAT_PILL: Record<Seat, string> = {
  fund: "fund console",
  pm: "PM console",
};

/** Page chrome, shared by the public site and the two consoles.
 *
 *  The three sides deliberately look related but not identical: each console
 *  gets a coloured rail under the masthead, so anyone glancing at a screenshot
 *  can tell in a quarter second whose eyes they are looking through. Confusing
 *  those is the expensive mistake this product exists to prevent. */
export function Masthead({ seat }: { seat?: Seat }) {
  return (
    <header className="masthead">
      <div className="masthead-inner">
        <a href="/" className="wordmark">
          PodShop <span>Arena</span>
        </a>
        {seat ? (
          <div className="row" style={{ gap: 10 }}>
            <span className={`pill seat-pill seat-${seat}`}>{SEAT_PILL[seat]}</span>
            {seat === "fund" && (
              <a className="small muted" href="/manage">
                all pods
              </a>
            )}
          </div>
        ) : (
          <div className="tagline">A track record you don't have to take on faith</div>
        )}
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div className="footer-mark">
          PodShop <span>Arena</span>
        </div>
      </div>
    </footer>
  );
}

/** The frame every route sits in: sticky header, optional full-bleed hero,
 *  content column, dark footer bookending the dawn arc. */
export function Page({
  hero,
  seat,
  scope,
  children,
}: {
  hero?: ReactNode;
  seat?: Seat;
  /** What this seat can reach — printed in the rail, because "you are the PM"
   *  is abstract and "Meridian Global Macro only" is not. */
  scope?: string;
  children: ReactNode;
}) {
  return (
    <div className={seat ? `page page-owner page-${seat}` : "page"}>
      <Masthead seat={seat} />
      {seat && (
        <div className={`owner-rail rail-${seat}`}>
          <div className="owner-rail-inner">
            {seat === "fund" ? (
              <>
                <strong>FUND</strong> · {scope ?? "every pod on the platform"} · none of
                this has crossed the wire
              </>
            ) : (
              <strong>PORTFOLIO MANAGER</strong>
            )}
          </div>
        </div>
      )}
      {hero}
      <main className="shell">{children}</main>
      <SiteFooter />
    </div>
  );
}
