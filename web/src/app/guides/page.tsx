import type { Metadata } from "next";
import Link from "next/link";
import { GOOGLE_DEINDEX_URL, PLATFORMS } from "@/lib/platforms";

export const metadata: Metadata = { title: "Platform guides" };

export default function GuidesPage() {
  return (
    <div className="container section">
      <h1>Platform guides</h1>
      <p style={{ marginTop: "var(--space-sm)" }}>
        How to report on each site, step by step. Under India&apos;s IT Rules, platforms must
        act within 24 hours of a complaint about intimate or morphed images.
      </p>

      <ul className="rows">
        {PLATFORMS.map((p) => (
          <li key={p.id}>
            <h3>
              <Link href={`/guides/${p.id}`}>{p.name}</Link>
            </h3>
            <p className="small muted">{p.domains.join(", ")}</p>
            <span className="small num">Must act in {p.expectedHours} hours</span>
          </li>
        ))}
      </ul>

      <div className="well well--moss stack" style={{ marginTop: "var(--space-xl)" }}>
        <h2>Site not listed?</h2>
        <p>
          You can still act. Contact the site&apos;s owner or its hosting company, and ask Google
          to remove the page from search results, which works even if the site refuses.
        </p>
        <a className="btn" href={GOOGLE_DEINDEX_URL} target="_blank" rel="noreferrer">
          Google&apos;s removal form
        </a>
      </div>
    </div>
  );
}
