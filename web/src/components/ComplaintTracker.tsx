"use client";

import { useState } from "react";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { Complaint, ComplaintStatus, Platform } from "@/lib/types";

// Tracks each complaint for one link through its lifecycle (section 18.5).
// Every step is recorded by the user: Nivra can't see what platforms do.

export const COMPLAINTS_CHANGED = "nivra:complaints-changed";
export const announceComplaintsChanged = () => window.dispatchEvent(new Event(COMPLAINTS_CHANGED));

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "Something went wrong. Please try again.";

const ACTION: Partial<Record<ComplaintStatus, string>> = {
  submitted_by_user: "I've submitted it",
  submission_confirmed: "They confirmed receipt",
  response_received: "They replied",
  resolved: "It's been removed",
  rejected: "They refused",
  discarded: "Discard",
};

const TONE: Record<ComplaintStatus, string> = {
  draft_generated: "neutral",
  user_approved: "neutral",
  submitted_by_user: "neutral",
  submission_confirmed: "neutral",
  response_received: "neutral",
  resolved: "good",
  rejected: "warn",
  discarded: "neutral",
};

const when = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export default function ComplaintTracker({
  complaints,
  platform,
  onChanged,
}: {
  complaints: Complaint[];
  platform: Platform | null;
  onChanged: () => void;
}) {
  if (complaints.length === 0) return null;
  return (
    <div className="stack">
      <h3>Complaints</h3>
      {complaints.map((c) => (
        <ComplaintCard key={c.id} c={c} platform={platform} onChanged={onChanged} />
      ))}
    </div>
  );
}

function ComplaintCard({
  c,
  platform,
  onChanged,
}: {
  c: Complaint;
  platform: Platform | null;
  onChanged: () => void;
}) {
  const [pending, setPending] = useState<ComplaintStatus | null>(null);
  const [channel, setChannel] = useState(platform?.channels[0]?.label ?? "other");
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const needsForm = (s: ComplaintStatus) =>
    s === "submitted_by_user" || s === "submission_confirmed" || s === "response_received";

  async function apply(status: ComplaintStatus) {
    setBusy(true);
    setError("");
    try {
      const mech = platform?.channels.find((m) => m.label === channel);
      await api.updateComplaint(c.id, {
        status,
        note: note.trim() || undefined,
        reference: reference.trim() || undefined,
        channel_kind: status === "submitted_by_user" ? (mech?.kind ?? "other") : undefined,
        channel_label: status === "submitted_by_user" ? (mech?.label ?? "Other") : undefined,
      });
      setPending(null);
      setNote("");
      setReference("");
      onChanged();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  // Assistant drafts are approved in the Assistant box (that resumes the agent).
  const actions = c.next_statuses.filter(
    (s) => !(c.status === "draft_generated" && s === "user_approved"),
  );

  return (
    <div className="well stack">
      <div className="actions" style={{ justifyContent: "space-between" }}>
        <span className="small">
          <strong>{c.subject}</strong>
          <span className="muted">
            {" "}
            ({c.source === "llm" ? "assistant draft" : "template"}
            {c.reference ? `, ref. ${c.reference}` : ""})
          </span>
        </span>
        <span className="badge" data-tone={TONE[c.status]}>
          {c.status_label}
        </span>
      </div>
      {c.status === "draft_generated" && (
        <p className="small muted">Approve or discard this draft in the Assistant box.</p>
      )}
      {c.status === "submitted_by_user" && platform && (
        <p className="small muted">
          {platform.name} should act within {platform.expectedHours} hours.{" "}
          {platform.trackingNote ?? ""}
        </p>
      )}

      {pending && needsForm(pending) ? (
        <div className="stack">
          {pending === "submitted_by_user" && (
            <div className="field" style={{ marginBottom: 0 }}>
              <label htmlFor={`ch-${c.id}`}>Where did you send it?</label>
              <select
                id={`ch-${c.id}`}
                className="input"
                value={channel}
                onChange={(e) => setChannel(e.target.value)}
              >
                {platform?.channels.map((m) => (
                  <option key={m.label} value={m.label}>
                    {m.label}
                  </option>
                ))}
                <option value="other">Somewhere else</option>
              </select>
            </div>
          )}
          {pending !== "response_received" && (
            <div className="field" style={{ marginBottom: 0 }}>
              <label htmlFor={`ref-${c.id}`}>Reference or ticket number (optional)</label>
              <input
                id={`ref-${c.id}`}
                className="input"
                value={reference}
                maxLength={120}
                onChange={(e) => setReference(e.target.value)}
              />
            </div>
          )}
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor={`note-${c.id}`}>Note for your records (optional)</label>
            <input
              id={`note-${c.id}`}
              className="input"
              value={note}
              maxLength={280}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          <div className="actions">
            <button className="btn btn--primary btn--small" disabled={busy} onClick={() => apply(pending)}>
              Save
            </button>
            <button className="btn btn--ghost btn--small" onClick={() => setPending(null)}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        actions.length > 0 && (
          <div className="actions">
            {actions.map((s) => (
              <button
                key={s}
                className={`btn btn--small ${s === "discarded" ? "btn--ghost" : ""}`}
                disabled={busy}
                onClick={() => (needsForm(s) ? setPending(s) : apply(s))}
              >
                {ACTION[s] ?? s}
              </button>
            ))}
          </div>
        )
      )}

      <details>
        <summary className="small" style={{ cursor: "pointer" }}>
          History and full text
        </summary>
        <ul className="timeline" style={{ marginTop: "var(--space-xs)" }}>
          {[...c.events].reverse().map((e, i) => (
            <li key={i}>
              <time className="num">{when(e.at)}</time>
              {e.note}
            </li>
          ))}
        </ul>
        <div className="notice" style={{ marginTop: "var(--space-sm)" }}>
          {c.body}
        </div>
      </details>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
