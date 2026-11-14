"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import AccountGate from "@/components/AccountGate";
import * as api from "@/lib/api";
import type { NivraNotification } from "@/lib/types";

// Updates from monitoring and deadlines (section 20). Nivra only tells you what
// it noticed; you check and record what actually happened.

const KIND_LABEL: Record<NivraNotification["kind"], string> = {
  match: "Possible match",
  deadline: "Deadline",
  page_gone: "Page no longer loads",
  page_back: "Page may be back",
  system: "Nivra",
};

export default function NotificationsView() {
  const [state, setState] = useState<"loading" | "locked" | "open">("loading");
  const [items, setItems] = useState<NivraNotification[]>([]);

  const load = useCallback(async () => {
    const me = await api.getMe().catch(() => null);
    if (!me) return setState("locked");
    setItems(await api.listNotifications());
    setState("open");
  }, []);

  useEffect(() => {
    // Initial load from the server.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  if (state === "loading") return <div className="container narrow section"><p className="muted">Loading</p></div>;
  if (state === "locked") return <AccountGate onOpen={() => load()} />;

  const unread = items.filter((n) => !n.read).length;
  return (
    <div className="container narrow section stack-lg">
      <div className="actions" style={{ justifyContent: "space-between" }}>
        <h1>Updates</h1>
        <div className="actions">
          {unread > 0 && (
            <button className="btn btn--small" onClick={async () => { await api.markAllNotificationsRead(); await load(); }}>
              Mark all as read
            </button>
          )}
          <Link className="btn btn--small btn--ghost" href="/settings">Settings</Link>
        </div>
      </div>
      <p className="small muted">
        Nivra tells you what it noticed while watching pages and deadlines. It never marks anything as
        removed or resolved on its own.
      </p>
      {items.length === 0 ? (
        <p className="well">No updates yet.</p>
      ) : (
        <ul className="links">
          {items.map((n) => (
            <li key={n.id} className="link-item">
              <div className="stack" style={{ paddingBlock: "var(--space-md)" }}>
                <div className="actions" style={{ justifyContent: "space-between" }}>
                  <strong style={{ color: "var(--color-ink)" }}>{n.title}</strong>
                  <span className="badge" data-tone={n.read ? "neutral" : "warn"}>
                    {n.read ? KIND_LABEL[n.kind] : `New: ${KIND_LABEL[n.kind]}`}
                  </span>
                </div>
                <p className="small">{n.body}</p>
                <div className="actions">
                  <Link className="btn btn--small" href={n.href}
                    onClick={() => { if (!n.read) void api.markNotificationRead(n.id); }}>
                    Open
                  </Link>
                  {!n.read && (
                    <button className="btn btn--ghost btn--small"
                      onClick={async () => { await api.markNotificationRead(n.id); await load(); }}>
                      Mark as read
                    </button>
                  )}
                  <span className="small muted num">
                    {new Date(n.created_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
