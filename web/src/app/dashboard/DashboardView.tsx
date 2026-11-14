"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import AccountGate from "@/components/AccountGate";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import { CATEGORY_LABEL } from "@/lib/notices";
import type { Account, Overview } from "@/lib/types";

// The central workspace (section 18.8): one view of protection, discovery,
// cases and complaints, and what needs the user's attention.

export default function DashboardView() {
  const [state, setState] = useState<"loading" | "locked" | "open" | "offline">("loading");
  const [account, setAccount] = useState<Account | null>(null);
  const [o, setO] = useState<Overview | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const me = await api.getMe();
      if (!me) return setState("locked");
      setAccount(me);
      setO(await api.getOverview());
      setState("open");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
      setState("offline");
    }
  }, []);

  useEffect(() => {
    // Initial load from the server.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  if (state === "loading") {
    return <div className="container narrow section"><p className="muted">Opening your account</p></div>;
  }
  if (state === "offline") {
    return (
      <div className="container narrow section stack">
        <h1>We can&apos;t open your account right now</h1>
        <p>{error}</p>
        <button className="btn btn--primary" onClick={() => load()}>Try again</button>
      </div>
    );
  }
  if (state === "locked" || !o || !account) {
    return <AccountGate allowCreate onOpen={() => load()} />;
  }

  const attention: { text: string; href: string; action: string }[] = [];
  if (o.matches_to_review) attention.push({
    text: `${o.matches_to_review} possible match${o.matches_to_review === 1 ? "" : "es"} waiting for your decision.`,
    href: "/protect", action: "Review" });
  if (o.approvals_waiting) attention.push({
    text: `${o.approvals_waiting} assistant draft${o.approvals_waiting === 1 ? "" : "s"} or plan${o.approvals_waiting === 1 ? "" : "s"} waiting for your approval.`,
    href: "/case", action: "Open" });
  if (o.pending_responses) attention.push({
    text: `${o.pending_responses} complaint${o.pending_responses === 1 ? "" : "s"} sent and waiting for a platform's reply.`,
    href: "/case", action: "Check" });

  const stats: [number, string][] = [
    [o.protected_images, "protected images"],
    [o.active_monitoring, "active"],
    [o.matches_found, "matches found"],
    [o.matches_to_review, "to review"],
    [o.confirmed_incidents, "cases"],
    [o.drafts, "notices drafted"],
    [o.submitted, "complaints sent"],
    [o.pending_responses, "awaiting reply"],
    [o.resolved + o.links_removed > 0 ? Math.max(o.resolved, o.links_removed) : 0, "removed"],
  ];

  return (
    <div className="container">
      <div className="dash-head">
        <div>
          <h1>Dashboard</h1>
          <p style={{ marginTop: "var(--space-sm)" }}>Everything in one place. Nothing happens without you.</p>
        </div>
        <div className="slip">
          <p className="label">Nivra ID</p>
          <p className="slip__id num">{account.account_code}</p>
        </div>
      </div>

      <section aria-label="Summary" className="stats">
        {stats.map(([n, label]) => (
          <div key={label}>
            <strong className="num">{n}</strong>
            <span className="small muted">{label}</span>
          </div>
        ))}
      </section>

      <section className="section stack" aria-labelledby="att-h">
        <h2 id="att-h">Needs your attention</h2>
        {attention.length === 0 ? (
          <p className="well">Nothing right now.</p>
        ) : (
          <ul className="rows">
            {attention.map((a) => (
              <li key={a.text}>
                <p>{a.text}</p>
                <span />
                <Link className="btn btn--small" href={a.href}>{a.action}</Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="section stack" aria-labelledby="cases-h" style={{ paddingTop: 0 }}>
        <div className="actions" style={{ justifyContent: "space-between" }}>
          <h2 id="cases-h">Your cases</h2>
          <Link className="btn btn--primary btn--small" href="/start">Start a case</Link>
        </div>
        {o.cases.length === 0 ? (
          <p className="well">No cases yet.</p>
        ) : (
          <ul className="rows">
            {o.cases.map((c, i) => (
              <li key={c.id}>
                <h3>Case {i + 1}</h3>
                <p className="small">
                  {CATEGORY_LABEL[c.category]}.{" "}
                  <span className="muted num">{c.links} link{c.links === 1 ? "" : "s"}, {c.removed} removed</span>
                </p>
                <Link className="btn btn--small" href={`/case#${c.id}`}>Open</Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="section stack" style={{ paddingTop: 0 }}>
        <div className="actions">
          <Link className="btn" href="/protect">Protected images and page checks</Link>
          <Link className="btn btn--ghost" href="/help">Get help now</Link>
        </div>
      </section>
    </div>
  );
}
