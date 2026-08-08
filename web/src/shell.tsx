import type { ReactNode } from "react";

/** Page chrome, shared by the public site and the manager console.
 *
 *  The two sides deliberately look related but not identical: the console adds
 *  an onyx rail under the masthead, so a manager glancing at a screenshot can
 *  tell in a quarter second whether they are looking at their own view or at
 *  what they published. Confusing those two is the expensive mistake this
 *  product exists to prevent. */
export function Masthead({ mode }: { mode?: "owner" }) {
  return (
    <header className="masthead">
      <div className="masthead-inner">
        <a href="/" className="wordmark">
          PodShop <span>Arena</span>
        </a>
        {mode === "owner" ? (
          <div className="row" style={{ gap: 10 }}>
            <span className="pill">manager console</span>
            <a className="small muted" href="/manage">
              all funds
            </a>
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
        <div className="footer-mark">The signature was in your inbox the whole time.</div>
      </div>
    </footer>
  );
}

/** The frame every route sits in: sticky header, optional full-bleed hero,
 *  content column, dark footer bookending the dawn arc. */
export function Page({
  hero,
  mode,
  children,
}: {
  hero?: ReactNode;
  mode?: "owner";
  children: ReactNode;
}) {
  return (
    <div className={mode === "owner" ? "page page-owner" : "page"}>
      <Masthead mode={mode} />
      {mode === "owner" && (
        <div className="owner-rail">
          <div className="owner-rail-inner">
            You're looking at everything. None of this has crossed the wire.
          </div>
        </div>
      )}
      {hero}
      <main className="shell">{children}</main>
      <SiteFooter />
    </div>
  );
}

