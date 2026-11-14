"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  closeCase,
  deleteCase,
  getCase,
  getOpenCaseId,
  isOverdue,
  makeLink,
  saveCase,
  unlockCase,
  withStatus,
} from "@/lib/caseStore";
import { CATEGORY_LABEL, generateNotice } from "@/lib/notices";
import {
  CLOUDFLARE_ABUSE_URL,
  CYBERCRIME_URL,
  GOOGLE_DEINDEX_URL,
  STOPNCII_URL,
  getPlatform,
  hostnameOf,
  splitLinks,
} from "@/lib/platforms";
import type { CaseLink, LinkStatus, NivraCase, Platform } from "@/lib/types";

// The case dashboard (blueprint 10.9, /case). Shows the unlock form when no
// case is open in this tab, otherwise every link with its status and next step.

type View = "loading" | "locked" | "open";

export default function CaseView() {
  const [view, setView] = useState<View>("loading");
  const [c, setC] = useState<NivraCase | null>(null);

  useEffect(() => {
    const id = getOpenCaseId();
    const found = id ? getCase(id) : null;
    // Reading browser storage has to happen after mount, so this effect
    // sets state once on load.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setC(found);
    setView(found ? "open" : "locked");
  }, []);

  function update(next: NivraCase) {
    saveCase(next);
    setC(next);
  }

  if (view === "loading") {
    return (
      <div className="container narrow section">
        <p className="muted">Opening your case</p>
      </div>
    );
  }

  if (view === "locked" || !c) {
    return (
      <Unlock
        onOpen={(opened) => {
          setC(opened);
          setView("open");
        }}
      />
    );
  }

  return (
    <Dashboard
      c={c}
      onChange={update}
      onLock={() => {
        closeCase();
        setC(null);
        setView("locked");
      }}
    />
  );
}

/* ---------------- Unlock ---------------- */

function Unlock({ onOpen }: { onOpen: (c: NivraCase) => void }) {
  const [id, setId] = useState("");
  const [pass, setPass] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const c = await unlockCase(id, pass);
    setBusy(false);
    if (!c) return setError("That Case ID and passphrase don't match a case in this browser.");
    onOpen(c);
  }

  return (
    <div className="container narrow section">
      <h1>Open your case</h1>
      <p style={{ margin: "var(--space-sm) 0 var(--space-xl)" }}>
        Enter the Case ID you were given and your passphrase.
      </p>
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="cid">Case ID</label>
          <input
            id="cid"
            className="input num"
            placeholder="NV-XXXX-XXXX"
            value={id}
            onChange={(e) => setId(e.target.value)}
            autoComplete="off"
            autoCapitalize="characters"
          />
        </div>
        <div className="field">
          <label htmlFor="pass">Passphrase</label>
          <input
            id="pass"
            type="password"
            className="input"
            value={pass}
            onChange={(e) => setPass(e.target.value)}
            autoComplete="current-password"
          />
        </div>
        {error && <p className="error">{error}</p>}
        <div className="actions" style={{ marginTop: "var(--space-lg)" }}>
          <button className="btn btn--primary" disabled={busy || !id || !pass}>
            {busy ? "Checking" : "Open case"}
          </button>
          <Link href="/start" className="btn btn--ghost">
            Start a new case instead
          </Link>
        </div>
      </form>
    </div>
  );
}

/* ---------------- Dashboard ---------------- */

const STATUS_LABEL: Record<LinkStatus, string> = {
  found: "Not reported yet",
  reported: "Waiting for reply",
  removed: "Removed",
  rejected: "Refused",
  escalated: "Escalated",
  reappeared: "Back online",
};

function badgeFor(link: CaseLink, platform?: Platform) {
  if (isOverdue(link, platform?.expectedHours ?? 24)) {
    return { label: "Deadline passed", tone: "warn" };
  }
  const tone =
    link.status === "removed"
      ? "good"
      : link.status === "rejected" || link.status === "reappeared"
        ? "warn"
        : "neutral";
  return { label: STATUS_LABEL[link.status], tone };
}

function Dashboard({
  c,
  onChange,
  onLock,
}: {
  c: NivraCase;
  onChange: (c: NivraCase) => void;
  onLock: () => void;
}) {
  const [newLinks, setNewLinks] = useState("");
  const [addError, setAddError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const removed = c.links.filter((l) => l.status === "removed").length;
  const waiting = c.links.filter((l) => l.status === "reported").length;
  const todo = c.links.length - removed - waiting;

  function setLink(next: CaseLink) {
    onChange({ ...c, links: c.links.map((l) => (l.id === next.id ? next : l)) });
  }

  function addLinks(e: React.FormEvent) {
    e.preventDefault();
    const made = splitLinks(newLinks)
      .map(makeLink)
      .filter((l): l is CaseLink => l !== null);
    if (made.length === 0) return setAddError("Paste at least one valid link.");
    setAddError("");
    setNewLinks("");
    onChange({ ...c, links: [...c.links, ...made] });
  }

  return (
    <div className="container">
      <div className="dash-head">
        <div>
          <p className="label">{CATEGORY_LABEL[c.category]}</p>
          <h1>Your case</h1>
          <div className="tally">
            <div>
              <strong className="num">{todo}</strong>
              <span className="small muted">to report</span>
            </div>
            <div>
              <strong className="num">{waiting}</strong>
              <span className="small muted">waiting for reply</span>
            </div>
            <div>
              <strong className="num">{removed}</strong>
              <span className="small muted">removed</span>
            </div>
          </div>
        </div>
        <div className="slip">
          <p className="label">Case ID</p>
          <p className="slip__id num">{c.id}</p>
          <div className="actions">
            <button className="btn btn--small" onClick={onLock}>
              Lock case
            </button>
          </div>
        </div>
      </div>

      <section aria-labelledby="links-h" style={{ marginBottom: "var(--space-2xl)" }}>
        <h2 id="links-h" style={{ marginBottom: "var(--space-md)" }}>
          Links
        </h2>
        {c.links.length === 0 ? (
          <p className="well">No links yet. Add the first one below.</p>
        ) : (
          <ul className="links">
            {c.links.map((l, i) => (
              <LinkRow key={l.id} link={l} c={c} onChange={setLink} defaultOpen={i === 0} />
            ))}
          </ul>
        )}

        <form onSubmit={addLinks} className="field" style={{ marginTop: "var(--space-xl)" }}>
          <label htmlFor="add">Found it somewhere else?</label>
          <textarea
            id="add"
            className="textarea"
            style={{ minHeight: "5rem" }}
            placeholder="Paste one or more links"
            value={newLinks}
            onChange={(e) => setNewLinks(e.target.value)}
          />
          {addError && <p className="error">{addError}</p>}
          <div>
            <button className="btn">Add links</button>
          </div>
        </form>
      </section>

      <section className="well well--moss">
        <div className="stack">
          <h2>Stop it coming back</h2>
          <p>
            Register the image with StopNCII. It makes a fingerprint on your device, so Facebook,
            Instagram, TikTok, Reddit and other partners can block re-uploads. The image is never
            sent.
          </p>
          <a className="btn" href={STOPNCII_URL} target="_blank" rel="noreferrer">
            Open StopNCII.org
          </a>
        </div>
      </section>

      <section className="section stack">
        <h2>Case settings</h2>
        <div className="field" style={{ maxWidth: "28rem" }}>
          <label htmlFor="dn">Name to sign notices with</label>
          <input
            id="dn"
            className="input"
            value={c.displayName}
            placeholder="Your name"
            onChange={(e) => onChange({ ...c, displayName: e.target.value })}
            autoComplete="off"
          />
        </div>
        {!confirmDelete ? (
          <button className="btn btn--danger btn--small" onClick={() => setConfirmDelete(true)}>
            Delete this case
          </button>
        ) : (
          <div className="well well--clay stack">
            <p>
              This permanently deletes the case and its history from this browser. It can&apos;t
              be undone.
            </p>
            <div className="actions">
              <button
                className="btn btn--danger btn--small"
                onClick={() => {
                  deleteCase(c.id);
                  onLock();
                }}
              >
                Yes, delete it
              </button>
              <button className="btn btn--small" onClick={() => setConfirmDelete(false)}>
                Keep it
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

/* ---------------- One link ---------------- */

function LinkRow({
  link,
  c,
  onChange,
  defaultOpen,
}: {
  link: CaseLink;
  c: NivraCase;
  onChange: (l: CaseLink) => void;
  defaultOpen: boolean;
}) {
  const platform = getPlatform(link.platformId);
  const host = hostnameOf(link.url) ?? link.url;
  const badge = badgeFor(link, platform);
  const overdue = isOverdue(link, platform?.expectedHours ?? 24);
  const notice = generateNotice({
    url: link.url,
    platform: platform ?? null,
    category: c.category,
    selfTaken: c.selfTaken,
    displayName: c.displayName,
  });
  const [copied, setCopied] = useState<"" | "body" | "subject">("");

  async function copy(text: string, which: "body" | "subject") {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(which);
      setTimeout(() => setCopied(""), 1800);
    } catch {}
  }

  const emailChannel = platform?.channels.find((ch) => ch.kind === "email");
  const needsEscalation = overdue || link.status === "rejected";

  return (
    <li className="link-item">
      <details open={defaultOpen}>
        <summary>
          <span style={{ minWidth: 0 }}>
            <span className="link-item__url" style={{ display: "block" }}>
              {host}
              <span className="muted">{new URL(link.url).pathname.replace(/\/$/, "")}</span>
            </span>
            <span className="small muted">{platform?.name ?? "Website not in our directory"}</span>
          </span>
          <span className="badge" data-tone={badge.tone}>
            {badge.label}
          </span>
        </summary>

        <div className="link-item__body">
          {/* Left: the notice */}
          <div className="stack">
            <h3>Your notice</h3>
            <p className="small muted">
              Grounds: India&apos;s IT Rules 2021 and IT Act
              {c.selfTaken ? ", plus your copyright" : ""}. A template, not legal advice.
            </p>
            <div className="field" style={{ marginBottom: 0 }}>
              <span className="label">Subject</span>
              <div className="notice">{notice.subject}</div>
            </div>
            <div className="notice">{notice.body}</div>
            <div className="actions">
              <button className="btn btn--small" onClick={() => copy(notice.body, "body")}>
                {copied === "body" ? "Copied" : "Copy notice"}
              </button>
              <button className="btn btn--small" onClick={() => copy(notice.subject, "subject")}>
                {copied === "subject" ? "Copied" : "Copy subject"}
              </button>
              {emailChannel?.target && (
                <a
                  className="btn btn--small"
                  href={`mailto:${emailChannel.target}?subject=${encodeURIComponent(
                    notice.subject,
                  )}&body=${encodeURIComponent(notice.body)}`}
                >
                  Open in email
                </a>
              )}
            </div>
          </div>

          {/* Right: where to send, status, next step */}
          <div className="stack-lg">
            <div className="well stack">
              <h3>Where to send it</h3>
              {platform ? (
                <>
                  <ul className="timeline">
                    {platform.channels.map((ch) => (
                      <li key={ch.label}>
                        {ch.kind === "form" && ch.target ? (
                          <a href={ch.target} target="_blank" rel="noreferrer">
                            {ch.label}
                          </a>
                        ) : ch.kind === "email" && ch.target ? (
                          <span>
                            {ch.label}: <span className="num">{ch.target}</span>
                          </span>
                        ) : (
                          <span>{ch.label}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                  {platform.inAppSteps && (
                    <ol className="ladder small">
                      {platform.inAppSteps.map((s) => (
                        <li key={s}>
                          <span>{s}</span>
                        </li>
                      ))}
                    </ol>
                  )}
                  <p className="small">
                    <Link href={`/guides/${platform.id}`}>Full {platform.name} guide</Link>
                  </p>
                </>
              ) : (
                <ol className="ladder small">
                  <li>
                    <span>
                      Look for a &ldquo;Contact&rdquo;, &ldquo;Abuse&rdquo; or &ldquo;DMCA&rdquo;
                      page on {host} and send the notice there.
                    </span>
                  </li>
                  <li>
                    <span>
                      Find the company hosting the site with a WHOIS lookup, and email the notice
                      to its abuse address.
                    </span>
                  </li>
                  <li>
                    <span>
                      If the site uses Cloudflare, report it at{" "}
                      <a href={CLOUDFLARE_ABUSE_URL} target="_blank" rel="noreferrer">
                        abuse.cloudflare.com
                      </a>
                      .
                    </span>
                  </li>
                </ol>
              )}
              <p className="small">
                Also ask Google to hide it from search:{" "}
                <a href={GOOGLE_DEINDEX_URL} target="_blank" rel="noreferrer">
                  Google&apos;s removal form
                </a>
              </p>
            </div>

            <StatusActions link={link} onChange={onChange} />

            {needsEscalation && <Escalation platform={platform} rejected={link.status === "rejected"} />}

            {link.status === "reported" && !overdue && (
              <p className="small muted">
                {platform?.name ?? "The site"} should act within{" "}
                <span className="num">{platform?.expectedHours ?? 24}</span> hours of your report.
                If it doesn&apos;t, come back and we&apos;ll show you the next step.{" "}
                <button
                  className="btn btn--ghost btn--small"
                  onClick={() => onChange({ ...link, deadlineOverride: true })}
                  title="Prototype only: simulate the deadline passing"
                >
                  Prototype: pretend the deadline passed
                </button>
              </p>
            )}

            <div>
              <h3 style={{ marginBottom: "var(--space-xs)" }}>History</h3>
              <ul className="timeline">
                {[...link.events].reverse().map((ev, i) => (
                  <li key={i}>
                    <time className="num" dateTime={ev.at}>
                      {new Date(ev.at).toLocaleString("en-IN", {
                        day: "numeric",
                        month: "short",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </time>
                    {ev.note ?? STATUS_LABEL[ev.status]}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </details>
    </li>
  );
}

function StatusActions({ link, onChange }: { link: CaseLink; onChange: (l: CaseLink) => void }) {
  const set = (s: LinkStatus, note: string) => onChange(withStatus(link, s, note));

  return (
    <div className="stack">
      <h3>Update the status</h3>
      <div className="actions">
        {(link.status === "found" || link.status === "reappeared") && (
          <button className="btn btn--primary btn--small" onClick={() => set("reported", "Notice sent")}>
            I&apos;ve sent the notice
          </button>
        )}
        {(link.status === "reported" || link.status === "escalated") && (
          <>
            <button className="btn btn--primary btn--small" onClick={() => set("removed", "Content removed")}>
              It&apos;s been removed
            </button>
            <button className="btn btn--small" onClick={() => set("rejected", "Platform refused")}>
              They refused
            </button>
          </>
        )}
        {link.status === "rejected" && (
          <button className="btn btn--small" onClick={() => set("escalated", "Escalated")}>
            I&apos;ve escalated it
          </button>
        )}
        {link.status === "removed" && (
          <button className="btn btn--small" onClick={() => set("reappeared", "Content came back")}>
            It&apos;s back online
          </button>
        )}
      </div>
    </div>
  );
}

function Escalation({ platform, rejected }: { platform?: Platform; rejected: boolean }) {
  return (
    <div className="well well--clay stack">
      <h3>{rejected ? "They refused. Here's what to do next" : "No reply in time. Here's the next step"}</h3>
      <ol className="ladder small">
        <li>
          <span>
            Send the notice again to {platform ? `${platform.name}'s` : "the site's"} Grievance
            Officer, saying the 24-hour deadline has passed. Large platforms list this contact on
            their India help pages.
          </span>
        </li>
        <li>
          <span>
            Appeal to the Grievance Appellate Committee at{" "}
            <a href="https://gac.gov.in/" target="_blank" rel="noreferrer">
              gac.gov.in
            </a>{" "}
            within 30 days of the platform&apos;s decision.
          </span>
        </li>
        <li>
          <span>
            Ask Google to remove the page from search using{" "}
            <a href={GOOGLE_DEINDEX_URL} target="_blank" rel="noreferrer">
              its removal form
            </a>
            .
          </span>
        </li>
        <li>
          <span>
            File a police complaint at{" "}
            <a href={CYBERCRIME_URL} target="_blank" rel="noreferrer">
              cybercrime.gov.in
            </a>{" "}
            or call <a href="tel:1930">1930</a>.
          </span>
        </li>
      </ol>
    </div>
  );
}
