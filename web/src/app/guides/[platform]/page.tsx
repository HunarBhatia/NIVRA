import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { GOOGLE_DEINDEX_URL, PLATFORMS, getPlatform } from "@/lib/platforms";

// Every known platform page is pre-built by generateStaticParams, so reading
// `params` without a Suspense boundary is fine; allow it to block (Next 16
// otherwise flags it in the dev overlay). Unknown platforms return 404.
export const instant = false;

export function generateStaticParams() {
  return PLATFORMS.map((p) => ({ platform: p.id }));
}

export async function generateMetadata({
  params,
}: PageProps<"/guides/[platform]">): Promise<Metadata> {
  const { platform } = await params;
  return { title: getPlatform(platform)?.name ?? "Guide" };
}

export default async function PlatformGuide({ params }: PageProps<"/guides/[platform]">) {
  const { platform: id } = await params;
  const p = getPlatform(id);
  if (!p) notFound();

  return (
    <div className="container narrow section stack-lg">
      <p className="small">
        <Link href="/guides">All platform guides</Link>
      </p>
      <div>
        <h1>Report on {p.name}</h1>
        {p.owner && <p className="muted small">Owned by {p.owner}</p>}
      </div>

      <div className="well">
        <p>
          Under India&apos;s IT Rules 2021, {p.name} must remove intimate or morphed images of
          you within <strong className="num">{p.expectedHours} hours</strong> of your complaint.
        </p>
      </div>

      {!p.verified && (
        <p className="well well--clay small">
          These details haven&apos;t been verified yet. Platforms change their reporting pages
          often, so check on {p.name}&apos;s own site.
        </p>
      )}

      <section className="stack">
        <h2>What they&apos;ll ask for</h2>
        <ul style={{ paddingLeft: "1.2rem" }}>
          {p.requiredInfo.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        <h3>Evidence to have ready</h3>
        <ul style={{ paddingLeft: "1.2rem" }}>
          {p.requiredEvidence.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        <h3>How you&apos;ll hear back</h3>
        <p className="small">{p.trackingNote ?? "Not known."}</p>
      </section>

      {p.inAppSteps && (
        <section className="stack">
          <h2>Steps</h2>
          <ol className="ladder">
            {p.inAppSteps.map((s) => (
              <li key={s}>
                <span>{s}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="stack">
        <h2>Where to report</h2>
        <ul className="rows">
          {p.channels.map((c) => (
            <li key={c.label}>
              <h3>{c.label}</h3>
              <p className="small muted">
                {c.kind === "in-app" ? "Inside the app or website" : c.target}
              </p>
              {c.kind === "form" && c.target && (
                <a className="btn btn--small" href={c.target} target="_blank" rel="noreferrer">
                  Open
                </a>
              )}
              {c.kind === "email" && c.target && (
                <a className="btn btn--small" href={`mailto:${c.target}`}>
                  Email
                </a>
              )}
              {c.kind === "in-app" && <span />}
            </li>
          ))}
        </ul>
        {p.notes && <p className="small">{p.notes}</p>}
      </section>

      <section className="well well--moss stack">
        <h2>Let Nivra write the notice</h2>
        <p>Start a case and we&apos;ll write a notice for this platform that cites the law.</p>
        <div className="actions">
          <Link className="btn btn--primary" href="/start">
            Start a case
          </Link>
          <a className="btn" href={GOOGLE_DEINDEX_URL} target="_blank" rel="noreferrer">
            Remove it from Google
          </a>
        </div>
      </section>

      <p className="small muted">
        These steps are prototype guidance and may be out of date.
      </p>
    </div>
  );
}
