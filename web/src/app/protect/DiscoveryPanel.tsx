"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { MatchExplainer, RecheckPlanner } from "@/components/Assistant";
import ScanView from "@/components/scan/ScanView";
import { jobCards } from "@/components/scan/LiveScan";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import { CATEGORY_LABEL } from "@/lib/notices";
import type { CaseSummary, Category, DiscoveredMatch, DiscoveryJob } from "@/lib/types";

// Phase 4: check a web page for protected images, then review what was found.
// Matches never show the found image (we don't keep it, and loading it from
// the site would reveal the user's visit). Nothing happens until the user
// confirms a match. See PROJECT_DETAILS.txt section 16.

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "Something went wrong. Please try again.";

const CLASS_TEXT: Record<DiscoveredMatch["classification"], string> = {
  exact: "Exact same file",
  high: "Very likely the same image",
  possible: "Possibly the same image",
};

function shortUrl(url: string) {
  try {
    const u = new URL(url);
    const path = u.pathname.length > 40 ? `${u.pathname.slice(0, 40)}…` : u.pathname;
    return `${u.hostname.replace(/^www\./, "")}${path === "/" ? "" : path}`;
  } catch {
    return url;
  }
}

function jobSummary(j: DiscoveryJob) {
  if (j.status === "queued") return "Waiting to start";
  if (j.status === "running") return "Checking the page";
  if (j.status === "failed") return j.error_message ?? "That page couldn't be checked.";
  const found = j.matches_found;
  const skipped = j.candidates_skipped ? `, ${j.candidates_skipped} couldn't be read` : "";
  return `Checked ${j.candidates_checked} image${j.candidates_checked === 1 ? "" : "s"}${skipped}. ${
    found === 0 ? "No matches found." : `${found} possible match${found === 1 ? "" : "es"} to review.`
  }`;
}

export default function DiscoveryPanel({ onMatchesChanged }: { onMatchesChanged?: (n: number) => void }) {
  const [url, setUrl] = useState("");
  const [jobs, setJobs] = useState<DiscoveryJob[]>([]);
  const [matches, setMatches] = useState<DiscoveredMatch[]>([]);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [j, m, c] = await Promise.all([api.listDiscoveryJobs(), api.listMatches(), api.listCases()]);
    setJobs(j);
    setMatches(m);
    setCases(c);
    onMatchesChanged?.(m.filter((x) => x.status === "pending").length);
  }, [onMatchesChanged]);

  useEffect(() => {
    // Initial load of jobs, matches and cases.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh().catch((e) => setError(errorText(e)));
  }, [refresh]);

  // While any job is queued or running, check again every second (live scan view).
  const active = jobs.some((j) => j.status === "queued" || j.status === "running");
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => refresh().catch(() => {}), 1000);
    return () => clearInterval(t);
  }, [active, refresh]);

  async function start(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const job = await api.createDiscoveryJob(url.trim());
      setJobs((list) => [job, ...list]);
      setUrl("");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const replace = (m: DiscoveredMatch) => {
    setMatches((list) => {
      const next = list.map((x) => (x.id === m.id ? m : x));
      onMatchesChanged?.(next.filter((x) => x.status === "pending").length);
      return next;
    });
  };

  const pending = matches.filter((m) => m.status === "pending");
  const confirmed = matches.filter((m) => m.status === "confirmed");
  const rejected = matches.filter((m) => m.status === "rejected");

  return (
    <>
      <section className="section stack" aria-labelledby="disc-h">
        <h2 id="disc-h">Check a web page for your images</h2>
        <p>
          Paste a link to a page (or an image) where your photo might be. Nivra visits it, looks at
          each image, compares fingerprints with your protected images, and keeps nothing but the
          result.
        </p>
        <form onSubmit={start} className="field" style={{ maxWidth: "40rem" }}>
          <label htmlFor="disc-url">Page link</label>
          <input
            id="disc-url"
            className="input"
            placeholder="https://example.com/thread/123"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            autoComplete="off"
          />
          <span className="hint">
            Pages that need a login, or ask automated tools not to visit, can&apos;t be checked.
            You can still report them in a case.
          </span>
          <div>
            <button className="btn btn--primary" disabled={busy || !url.trim()}>
              {busy ? "Starting" : "Check page"}
            </button>
          </div>
        </form>
        {error && <p className="error">{error}</p>}

        <RecheckPlanner onQueued={() => refresh().catch(() => {})} />

        {jobs[0] && (
          <ScanView
            key={jobs[0].id}
            stage={jobs[0].stage ?? (jobs[0].status === "running" ? "scanning" : jobs[0].status)}
            title={jobs[0].page_title ? `${jobs[0].page_title} (${jobs[0].input_url})` : jobs[0].input_url}
            cards={jobCards(jobs[0])}
            error={jobs[0].status === "failed" ? jobs[0].error_message : null}
          />
        )}

        {jobs.length > 1 && (
          <div>
            <h3 style={{ marginBottom: "var(--space-xs)" }}>Earlier checks</h3>
            <ul className="rows" aria-live="polite">
              {jobs.slice(1, 6).map((j) => (
                <li key={j.id}>
                  <h3 className="small" style={{ fontSize: "var(--text-base)" }}>
                    {j.page_title ?? shortUrl(j.input_url)}
                  </h3>
                  <p className={`small ${j.status === "failed" ? "error" : "muted"}`}>{jobSummary(j)}</p>
                  <span
                    className="badge"
                    data-tone={j.status === "failed" ? "warn" : j.status === "done" ? "good" : "neutral"}
                  >
                    {j.status === "done" ? "Done" : j.status === "failed" ? "Couldn't check" : "In progress"}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="section stack" aria-labelledby="review-h" style={{ paddingTop: 0 }}>
        <h2 id="review-h">Matches to review</h2>
        {pending.length === 0 && confirmed.length === 0 ? (
          <p className="well">Nothing to review yet.</p>
        ) : (
          <p className="small">
            Nivra only suggests. You decide whether each one is really your image. Found images are
            never shown here: opening a page lets that site see your visit, so you may prefer a
            trusted friend to check it.
          </p>
        )}
        <ul className="links">
          {[...pending, ...confirmed].map((m) => (
            <MatchRow key={m.id} m={m} cases={cases} onChange={replace} onCasesChanged={refresh} />
          ))}
        </ul>
        {rejected.length > 0 && (
          <details>
            <summary className="small" style={{ cursor: "pointer" }}>
              Dismissed ({rejected.length})
            </summary>
            <ul className="links">
              {rejected.map((m) => (
                <MatchRow key={m.id} m={m} cases={cases} onChange={replace} onCasesChanged={refresh} />
              ))}
            </ul>
          </details>
        )}
      </section>
    </>
  );
}

function MatchRow({
  m,
  cases,
  onChange,
  onCasesChanged,
}: {
  m: DiscoveredMatch;
  cases: CaseSummary[];
  onChange: (m: DiscoveredMatch) => void;
  onCasesChanged: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [target, setTarget] = useState<string>(cases.length ? cases[cases.length - 1].id : "new");
  const [category, setCategory] = useState<Category>("intimate");
  const [addedCase, setAddedCase] = useState<string | null>(null);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const tone = m.status === "confirmed" ? "warn" : m.classification === "possible" ? "neutral" : "warn";
  const evidence = m.sha256_equal
    ? "Byte-for-byte the same file as your protected image."
    : `Visual difference ${m.phash_distance ?? "?"} of 64 from your protected image.`;

  return (
    <li className="link-item">
      <div className="stack" style={{ paddingBlock: "var(--space-md)" }}>
        <div className="actions" style={{ justifyContent: "space-between" }}>
          <span style={{ minWidth: 0 }}>
            <span className="link-item__url" style={{ display: "block" }}>
              {shortUrl(m.source_page_url)}
            </span>
            <span className="small muted">
              Matches &ldquo;{m.image_label || "your protected image"}&rdquo;
            </span>
          </span>
          <span className="badge" data-tone={tone}>
            {m.status === "confirmed" ? "Confirmed by you" : CLASS_TEXT[m.classification]}
          </span>
        </div>
        <p className="small muted">{evidence}</p>
        <MatchExplainer matchId={m.id} />
        <p className="small">
          <a href={m.source_page_url} target="_blank" rel="noreferrer noopener">
            Open the page in a new tab
          </a>{" "}
          <span className="muted">(the site will see this visit)</span>
        </p>

        {m.status === "pending" && (
          <div className="actions">
            <button
              className="btn btn--primary btn--small"
              disabled={busy}
              onClick={() => run(async () => onChange(await api.reviewMatch(m.id, "confirmed")))}
            >
              Yes, this is my image
            </button>
            <button
              className="btn btn--small"
              disabled={busy}
              onClick={() => run(async () => onChange(await api.reviewMatch(m.id, "rejected")))}
            >
              No, not mine
            </button>
          </div>
        )}

        {m.status === "rejected" && (
          <div>
            <button
              className="btn btn--ghost btn--small"
              disabled={busy}
              onClick={() => run(async () => onChange(await api.reviewMatch(m.id, "pending")))}
            >
              Undo
            </button>
          </div>
        )}

        {m.status === "confirmed" && !m.case_link_id && !addedCase && (
          <div className="well stack">
            <p className="small">Add this page to a case to get a takedown notice for it.</p>
            <div className="actions">
              <select
                className="input"
                style={{ width: "auto" }}
                aria-label="Which case"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              >
                {cases.map((c, i) => (
                  <option key={c.id} value={c.id}>
                    Case {i + 1}: {CATEGORY_LABEL[c.category]}
                  </option>
                ))}
                <option value="new">A new case</option>
              </select>
              {target === "new" && (
                <select
                  className="input"
                  style={{ width: "auto" }}
                  aria-label="What happened"
                  value={category}
                  onChange={(e) => setCategory(e.target.value as Category)}
                >
                  {(Object.keys(CATEGORY_LABEL) as Category[]).map((c) => (
                    <option key={c} value={c}>
                      {CATEGORY_LABEL[c]}
                    </option>
                  ))}
                </select>
              )}
              <button
                className="btn btn--primary btn--small"
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    const r = await api.addMatchToCase(
                      m.id,
                      target === "new" ? { category } : { case_id: target },
                    );
                    setAddedCase(r.case_id);
                    onChange({ ...m, case_link_id: r.link_id });
                    await onCasesChanged();
                  })
                }
              >
                Add to case
              </button>
            </div>
            <button
              className="btn btn--ghost btn--small"
              disabled={busy}
              onClick={() => run(async () => onChange(await api.reviewMatch(m.id, "pending")))}
            >
              Undo confirmation
            </button>
          </div>
        )}

        {m.status === "confirmed" && (m.case_link_id || addedCase) && (
          <p className="small">
            Added to a case. <Link href="/case">Open my case</Link> to get the notice.
          </p>
        )}
        {error && <p className="error">{error}</p>}
      </div>
    </li>
  );
}
