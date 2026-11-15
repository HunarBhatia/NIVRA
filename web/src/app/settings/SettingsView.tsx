"use client";

import { useCallback, useEffect, useState } from "react";
import AccountGate from "@/components/AccountGate";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { Account, NotificationPrefs, WatchedPage } from "@/lib/types";

// Monitoring and notification controls (section 20).

export const INTERVAL_LABEL: Record<number, string> = {
  12: "Every 12 hours",
  24: "Every day",
  72: "Every 3 days",
  168: "Every week",
};

const errorText = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong.");

export default function SettingsView() {
  const [state, setState] = useState<"loading" | "locked" | "open">("loading");
  const [account, setAccount] = useState<Account | null>(null);
  const [prefs, setPrefs] = useState<NotificationPrefs | null>(null);
  const [watches, setWatches] = useState<WatchedPage[]>([]);
  const [email, setEmailInput] = useState("");
  const [newUrl, setNewUrl] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const me = await api.getMe().catch(() => null);
    if (!me) return setState("locked");
    setAccount(me);
    const [p, w] = await Promise.all([api.getNotificationPrefs(), api.listWatches()]);
    setPrefs(p);
    setWatches(w);
    setState("open");
  }, []);

  useEffect(() => {
    // Initial load from the server.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function act(fn: () => Promise<unknown>, done?: string) {
    setError("");
    setMsg("");
    try {
      await fn();
      await load();
      if (done) setMsg(done);
    } catch (e) {
      setError(errorText(e));
    }
  }

  if (state === "loading") return <div className="container narrow section"><p className="muted">Loading</p></div>;
  if (state === "locked" || !prefs || !account) return <AccountGate onOpen={() => load()} />;

  const toggle = (field: keyof NotificationPrefs, label: string) => (
    <label className="check">
      <input type="checkbox" checked={Boolean(prefs[field])}
        onChange={(e) => act(() => api.updateNotificationPrefs({ [field]: e.target.checked }))} />
      <span>{label}</span>
    </label>
  );

  return (
    <div className="container narrow section stack-lg">
      <h1>Settings</h1>
      {msg && <p className="well well--moss small" role="status">{msg}</p>}
      {error && <p className="error" role="alert">{error}</p>}

      <section className="stack" aria-labelledby="mon-h">
        <h2 id="mon-h">Monitoring</h2>
        {toggle("monitoring_enabled", "Keep re-checking the pages I watch")}
        <p className="small muted">
          Switch this off to pause every scheduled check at once. Nothing is checked without you
          choosing to watch a page.
        </p>

        <h3>Pages I&apos;m watching</h3>
        {watches.length === 0 ? (
          <p className="well small">
            You&apos;re not watching any pages. Use &ldquo;Watch this page&rdquo; on a link in your case,
            or add one below.
          </p>
        ) : (
          <ul className="rows">
            {watches.map((w) => (
              <li key={w.id}>
                <h3 className="small" style={{ fontSize: "var(--text-base)", overflowWrap: "anywhere" }}>{w.host}</h3>
                <p className="small muted">
                  {w.enabled ? INTERVAL_LABEL[w.interval_hours] : "Paused"}
                  {w.last_checked_at ? `. Last checked ${new Date(w.last_checked_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}` : ". Not checked yet"}
                  {w.last_result === "not_found" ? " (page didn't load)" : ""}
                </p>
                <div className="actions">
                  <select className="input" style={{ width: "auto" }} aria-label="How often"
                    value={w.interval_hours}
                    onChange={(e) => act(() => api.updateWatch(w.id, { interval_hours: Number(e.target.value) }))}>
                    {Object.entries(INTERVAL_LABEL).map(([h, l]) => <option key={h} value={h}>{l}</option>)}
                  </select>
                  <button className="btn btn--small" onClick={() => act(() => api.updateWatch(w.id, { enabled: !w.enabled }))}>
                    {w.enabled ? "Pause" : "Resume"}
                  </button>
                  <button className="btn btn--ghost btn--small" onClick={() => act(() => api.removeWatch(w.id))}>
                    Stop watching
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
        <form className="actions" onSubmit={(e) => { e.preventDefault(); void act(() => api.addWatch({ url: newUrl }), "Page added.").then(() => setNewUrl("")); }}>
          <input className="input" style={{ flex: 1, minWidth: "14rem" }} placeholder="https://example.com/page"
            aria-label="Page to watch" value={newUrl} onChange={(e) => setNewUrl(e.target.value)} />
          <button className="btn btn--small" disabled={!newUrl.trim()}>Watch page</button>
        </form>
      </section>

      <section className="stack" aria-labelledby="not-h">
        <h2 id="not-h">Updates</h2>
        {toggle("notify_matches", "Possible matches found on watched pages")}
        {toggle("notify_page_changes", "Watched pages that stop loading or come back")}
        {toggle("notify_deadlines", "Platform deadlines coming up or passed")}
      </section>

      <section className="stack" aria-labelledby="em-h">
        <h2 id="em-h">Email (optional)</h2>
        <p className="small">
          Emails never contain details, only &ldquo;You have an update from Nivra&rdquo;, in case
          someone else sees your inbox. Your address is stored encrypted.
        </p>
        {account.has_email ? (
          <>
            <fieldset className="choices" style={{ marginBottom: 0 }}>
              <legend className="label" style={{ marginBottom: "var(--space-xs)" }}>Send me an email</legend>
              {([["off", "Never"], ["immediate", "When there's an update"], ["daily", "At most once a day"]] as const).map(([v, l]) => (
                <label key={v} className="choice">
                  <input type="radio" name="email_mode" checked={prefs.email_mode === v}
                    onChange={() => act(() => api.updateNotificationPrefs({ email_mode: v }))} />
                  <span><strong>{l}</strong></span>
                </label>
              ))}
            </fieldset>
            {prefs.email_backend === "console" && (
              <p className="hint">This server is in development mode, so emails are logged, not sent.</p>
            )}
            <div>
              <button className="btn btn--ghost btn--small" onClick={() => act(() => api.setEmail(null), "Email removed.")}>
                Remove my email
              </button>
            </div>
          </>
        ) : (
          <form className="actions" onSubmit={(e) => { e.preventDefault(); void act(() => api.setEmail(email.trim()), "Email saved.").then(() => setEmailInput("")); }}>
            <input className="input" type="email" style={{ flex: 1, minWidth: "14rem" }} placeholder="you@example.com"
              aria-label="Email address" value={email} onChange={(e) => setEmailInput(e.target.value)} autoComplete="email" />
            <button className="btn btn--small" disabled={!email.trim()}>Add email</button>
          </form>
        )}
      </section>
    </div>
  );
}
