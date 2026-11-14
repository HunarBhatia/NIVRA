"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import AccountGate from "@/components/AccountGate";
import * as api from "@/lib/api";
import { ApiError, isOverdue } from "@/lib/api";
import { CATEGORY_LABEL, generateNotice } from "@/lib/notices";
import {
  CLOUDFLARE_ABUSE_URL,
  CYBERCRIME_URL,
  GOOGLE_DEINDEX_URL,
  STOPNCII_URL,
  resolvePlatform,
  splitLinks,
} from "@/lib/platforms";
import type { Account, CaseLink, CaseSummary, LinkStatus, NivraCase, Platform } from "@/lib/types";

// The account dashboard (/case). Logged out: the unlock form. Logged in: the
// account's cases, each link with its notice, status and next step. All data
// comes from the backend API (backend/app/api/cases.py).

type View = "loading" | "locked" | "empty" | "open" | "offline";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "Something went wrong. Please try again.";

export default function CaseView() {
  const [view, setView] = useState<View>("loading");
  const [account, setAccount] = useState<Account | null>(null);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [current, setCurrent] = useState<NivraCase | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async (preferId?: string) => {
    try {
      const me = await api.getMe();
      setAccount(me);
      if (!me) return setView("locked");
      const list = await api.listCases();
      setCases(list);
      if (list.length === 0) {
        setCurrent(null);
        return setView("empty");
      }
      const pick = list.find((c) => c.id === preferId) ?? list[list.length - 1];
      setCurrent(await api.getCase(pick.id));
      setView("open");
    } catch (e) {
      setError(errorText(e));
      setView("offline");
    }
  }, []);

  useEffect(() => {
    // Loading data from the server once on mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function lock() {
    await api.logout().catch(() => {});
    setAccount(null);
    setCurrent(null);
    setView("locked");
  }

  if (view === "loading") {
    return (
      <div className="container narrow section">
        <p className="muted">Opening your account</p>
      </div>
    );
  }

  if (view === "offline") {
    return (
      <div className="container narrow section stack">
        <h1>We can&apos;t open your account right now</h1>
        <p>{error}</p>
        <div className="actions">
          <button className="btn btn--primary" onClick={() => load()}>
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (view === "locked" || !account) {
    return <AccountGate onOpen={() => load()} />;
  }

  if (view === "empty" || !current) {
    return (
      <div className="container narrow section stack">
        <p className="label num">Nivra ID {account.account_code}</p>
        <h1>No cases yet</h1>
        <p>Start a case to get notices written for each link.</p>
        <div className="actions">
          <Link href="/start" className="btn btn--primary">
            Start a case
          </Link>
          <button className="btn" onClick={lock}>
            Lock account
          </button>
        </div>
      </div>
    );
  }

  return (
    <Dashboard
      account={account}
      cases={cases}
      c={current}
      setCase={setCurrent}
      onSwitch={(id) => load(id)}
      onDeleted={() => load()}
      onLock={lock}
    />
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

function badgeFor(link: CaseLink, platform: Platform | null) {
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
  account,
  cases,
  c,
  setCase,
  onSwitch,
  onDeleted,
  onLock,
}: {
  account: Account;
  cases: CaseSummary[];
  c: NivraCase;
  setCase: (c: NivraCase) => void;
  onSwitch: (id: string) => void;
  onDeleted: () => void;
  onLock: () => void;
}) {
  const [newLinks, setNewLinks] = useState("");
  const [addError, setAddError] = useState("");
  const [name, setName] = useState(c.display_name);
  const [nameSaved, setNameSaved] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState("");

  const removed = c.links.filter((l) => l.status === "removed").length;
  const waiting = c.links.filter((l) => l.status === "reported").length;
  const todo = c.links.length - removed - waiting;

  function replaceLink(next: CaseLink) {
    setCase({ ...c, links: c.links.map((l) => (l.id === next.id ? next : l)) });
  }

  async function addLinks(e: React.FormEvent) {
    e.preventDefault();
    const urls = splitLinks(newLinks);
    if (urls.length === 0) return setAddError("Paste at least one valid link.");
    try {
      setCase(await api.addLinks(c.id, urls));
      setAddError("");
      setNewLinks("");
    } catch (err) {
      setAddError(errorText(err));
    }
  }

  async function saveName() {
    if (name === c.display_name) return;
    try {
      setCase(await api.updateCase(c.id, name));
      setNameSaved(true);
      setTimeout(() => setNameSaved(false), 1800);
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function removeCase() {
    try {
      await api.deleteCase(c.id);
      onDeleted();
    } catch (err) {
      setError(errorText(err));
    }
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
          {cases.length > 1 && (
            <div className="field" style={{ marginTop: "var(--space-lg)", maxWidth: "24rem" }}>
              <label htmlFor="switch">Your cases</label>
              <select
                id="switch"
                className="input"
                value={c.id}
                onChange={(e) => onSwitch(e.target.value)}
              >
                {cases.map((s, i) => (
                  <option key={s.id} value={s.id}>
                    Case {i + 1}: {CATEGORY_LABEL[s.category]} ({s.link_count} links)
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
        <div className="slip">
          <p className="label">Nivra ID</p>
          <p className="slip__id num">{account.account_code}</p>
          <div className="actions">
            <button className="btn btn--small" onClick={onLock}>
              Lock account
            </button>
            <Link href="/start" className="btn btn--small btn--ghost">
              New case
            </Link>
          </div>
        </div>
      </div>

      {error && (
        <p className="well well--clay error" role="alert" style={{ marginBottom: "var(--space-lg)" }}>
          {error}
        </p>
      )}

      <section aria-labelledby="links-h" style={{ marginBottom: "var(--space-2xl)" }}>
        <h2 id="links-h" style={{ marginBottom: "var(--space-md)" }}>
          Links
        </h2>
        {c.links.length === 0 ? (
          <p className="well">No links yet. Add the first one below.</p>
        ) : (
          <ul className="links">
            {c.links.map((l, i) => (
              <LinkRow
                key={l.id}
                link={l}
                c={c}
                onChange={replaceLink}
                onError={setError}
                defaultOpen={i === 0}
              />
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
            value={name}
            placeholder="Your name"
            onChange={(e) => setName(e.target.value)}
            onBlur={saveName}
            autoComplete="off"
          />
          <span className="hint" aria-live="polite">
            {nameSaved ? "Saved" : "Saved when you click away."}
          </span>
        </div>
        {!confirmDelete ? (
          <button className="btn btn--danger btn--small" onClick={() => setConfirmDelete(true)}>
            Delete this case
          </button>
        ) : (
          <div className="well well--clay stack">
            <p>
              This permanently deletes the case, its links and their history. It can&apos;t be
              undone.
            </p>
            <div className="actions">
              <button className="btn btn--danger btn--small" onClick={removeCase}>
                Yes, delete it
              </button>
              <button className="btn btn--small" onClick={() => setConfirmDelete(false)}>
                Keep it
              </button>
            </div>
          </div>
        )}
      </section>

      <DeleteAccount onDeleted={onLock} />
    </div>
  );
}

/* ---------------- Delete account ---------------- */

function DeleteAccount({ onDeleted }: { onDeleted: () => void }) {
  const [open, setOpen] = useState(false);
  const [pass, setPass] = useState("");
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.deleteAccount(pass);
      onDeleted();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section className="section stack" style={{ paddingTop: 0 }}>
      <h2>Your data</h2>
      <p className="small">
        You can delete your account at any time. This removes every case, link and history entry
        from Nivra&apos;s servers.
      </p>
      {!open ? (
        <div>
          <button className="btn btn--danger btn--small" onClick={() => setOpen(true)}>
            Delete my account and all data
          </button>
        </div>
      ) : (
        <form onSubmit={submit} className="well well--clay stack" style={{ maxWidth: "32rem" }}>
          <p>This can&apos;t be undone. Enter your passphrase to confirm.</p>
          <input
            type="password"
            className="input"
            aria-label="Passphrase"
            value={pass}
            onChange={(e) => setPass(e.target.value)}
            autoComplete="current-password"
          />
          {error && <p className="error">{error}</p>}
          <div className="actions">
            <button className="btn btn--danger btn--small" disabled={!pass}>
              Delete everything
            </button>
            <button type="button" className="btn btn--small" onClick={() => setOpen(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

/* ---------------- One link ---------------- */

function LinkRow({
  link,
  c,
  onChange,
  onError,
  defaultOpen,
}: {
  link: CaseLink;
  c: NivraCase;
  onChange: (l: CaseLink) => void;
  onError: (msg: string) => void;
  defaultOpen: boolean;
}) {
  const platform = resolvePlatform(link.url);
  const host = link.host;
  const badge = badgeFor(link, platform);
  const overdue = isOverdue(link, platform?.expectedHours ?? 24);
  const notice = generateNotice({
    url: link.url,
    platform,
    category: c.category,
    selfTaken: c.self_taken,
    displayName: c.display_name,
  });
  const [copied, setCopied] = useState<"" | "body" | "subject">("");
  const [busy, setBusy] = useState(false);

  async function copy(text: string, which: "body" | "subject") {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(which);
      setTimeout(() => setCopied(""), 1800);
    } catch {}
  }

  async function run(action: () => Promise<CaseLink>) {
    setBusy(true);
    try {
      onChange(await action());
    } catch (err) {
      onError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const emailChannel = platform?.channels.find((ch) => ch.kind === "email");
  const needsEscalation = overdue || link.status === "rejected";
  let path = "";
  try {
    path = new URL(link.url).pathname.replace(/\/$/, "");
  } catch {}

  return (
    <li className="link-item">
      <details open={defaultOpen}>
        <summary>
          <span style={{ minWidth: 0 }}>
            <span className="link-item__url" style={{ display: "block" }}>
              {host}
              <span className="muted">{path}</span>
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
              {c.self_taken ? ", plus your copyright" : ""}. A template, not legal advice.
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

            <StatusActions
              link={link}
              busy={busy}
              onSet={(s, note) => run(() => api.changeStatus(link.id, s, note))}
            />

            {needsEscalation && (
              <Escalation platform={platform} rejected={link.status === "rejected"} />
            )}

            {link.status === "reported" && !overdue && (
              <p className="small muted">
                {platform?.name ?? "The site"} should act within{" "}
                <span className="num">{platform?.expectedHours ?? 24}</span> hours of your report.
                If it doesn&apos;t, come back and we&apos;ll show you the next step.{" "}
                <button
                  className="btn btn--ghost btn--small"
                  disabled={busy}
                  onClick={() => run(() => api.simulateDeadline(link.id))}
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

function StatusActions({
  link,
  busy,
  onSet,
}: {
  link: CaseLink;
  busy: boolean;
  onSet: (s: LinkStatus, note: string) => void;
}) {
  return (
    <div className="stack">
      <h3>Update the status</h3>
      <div className="actions">
        {(link.status === "found" || link.status === "reappeared") && (
          <button
            className="btn btn--primary btn--small"
            disabled={busy}
            onClick={() => onSet("reported", "Notice sent")}
          >
            I&apos;ve sent the notice
          </button>
        )}
        {(link.status === "reported" || link.status === "escalated") && (
          <>
            <button
              className="btn btn--primary btn--small"
              disabled={busy}
              onClick={() => onSet("removed", "Content removed")}
            >
              It&apos;s been removed
            </button>
            <button
              className="btn btn--small"
              disabled={busy}
              onClick={() => onSet("rejected", "Platform refused")}
            >
              They refused
            </button>
          </>
        )}
        {link.status === "rejected" && (
          <button
            className="btn btn--small"
            disabled={busy}
            onClick={() => onSet("escalated", "Escalated")}
          >
            I&apos;ve escalated it
          </button>
        )}
        {link.status === "removed" && (
          <button
            className="btn btn--small"
            disabled={busy}
            onClick={() => onSet("reappeared", "Content came back")}
          >
            It&apos;s back online
          </button>
        )}
      </div>
    </div>
  );
}

function Escalation({ platform, rejected }: { platform: Platform | null; rejected: boolean }) {
  return (
    <div className="well well--clay stack">
      <h3>
        {rejected ? "They refused. Here's what to do next" : "No reply in time. Here's the next step"}
      </h3>
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
