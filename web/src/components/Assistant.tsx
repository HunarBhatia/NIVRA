"use client";

import { useEffect, useState } from "react";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { AgentRun, AgentStatus } from "@/lib/types";

// Front ends for the four AI agents (phase 5, PROJECT_DETAILS.txt 17).
// The assistant drafts, explains and plans. It never sends, submits or
// decides anything: every consequential step has an explicit approve button.

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "Something went wrong. Please try again.";

let statusPromise: Promise<AgentStatus> | null = null;
export function useAgentStatus() {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  useEffect(() => {
    statusPromise ??= api.agentStatus();
    statusPromise.then(setStatus).catch(() => setStatus(null));
  }, []);
  return status;
}

export function SourceNote({ usedLlm, status }: { usedLlm: boolean; status: AgentStatus | null }) {
  if (usedLlm) {
    return (
      <p className="small muted">
        Drafted by AI ({status?.model ?? "Gemini"}). It was sent only the case type and platform,
        never your name, links or images. Please read it before using it.
      </p>
    );
  }
  return (
    <p className="small muted">
      {status?.llm_available
        ? "The AI draft didn't pass our safety checks, so this is Nivra's standard template."
        : "AI drafting is switched off on this server, so this is Nivra's standard template."}
    </p>
  );
}

/* ---------------- Complaint draft for one link ---------------- */

export function NoticeAssistant({
  caseId,
  linkId,
  platformName,
}: {
  caseId: string;
  linkId: string;
  platformName?: string;
}) {
  const status = useAgentStatus();
  const [run, setRun] = useState<AgentRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api
      .listAgentRuns("complaint", linkId)
      .then((runs) => setRun(runs.find((r) => r.status === "completed" || r.status === "awaiting_approval") ?? null))
      .catch(() => {});
  }, [linkId]);

  async function act(fn: () => Promise<AgentRun>) {
    setBusy(true);
    setError("");
    try {
      setRun(await fn());
      // Drafts and approvals create/update tracked complaints (section 18.5).
      window.dispatchEvent(new Event("nivra:complaints-changed"));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const prepare = () => act(() => api.draftComplaint(caseId, linkId, platformName));

  return (
    <div className="well stack">
      <h3>Assistant</h3>
      {!run || run.status === "rejected" || run.status === "failed" ? (
        <>
          <p className="small">
            The assistant can prepare a notice for this link for you to review and approve.
          </p>
          {run?.status === "failed" && (
            <p className="error">The assistant couldn&apos;t finish. You can try again.</p>
          )}
          <div>
            <button className="btn btn--small" disabled={busy} onClick={prepare}>
              {busy ? "Preparing" : "Prepare a notice"}
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="small">
            <strong>{run.status === "completed" ? "Approved by you." : "Waiting for your approval."}</strong>{" "}
            {run.status === "completed"
              ? "Copy it and send it yourself, then mark the link as sent."
              : "Nothing is sent. Approve it to keep it as your notice for this link."}
          </p>
          {run.preview && (
            <>
              <div className="notice">
                <strong>{run.preview.subject}</strong>
                {"\n\n"}
                {run.preview.body}
              </div>
              <SourceNote usedLlm={run.used_llm} status={status} />
            </>
          )}
          <div className="actions">
            {run.status === "awaiting_approval" ? (
              <>
                <button
                  className="btn btn--primary btn--small"
                  disabled={busy}
                  onClick={() => act(() => api.decideRun(run.id, "approve"))}
                >
                  Approve this notice
                </button>
                <button
                  className="btn btn--small"
                  disabled={busy}
                  onClick={() => act(() => api.decideRun(run.id, "reject"))}
                >
                  Discard
                </button>
              </>
            ) : (
              <>
                <button
                  className="btn btn--small"
                  onClick={async () => {
                    if (!run.preview) return;
                    try {
                      await navigator.clipboard.writeText(`${run.preview.subject}\n\n${run.preview.body}`);
                      setCopied(true);
                      setTimeout(() => setCopied(false), 1800);
                    } catch {}
                  }}
                >
                  {copied ? "Copied" : "Copy approved notice"}
                </button>
                <button className="btn btn--ghost btn--small" disabled={busy} onClick={prepare}>
                  Prepare a new one
                </button>
              </>
            )}
          </div>
        </>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

/* ---------------- Follow-ups across all cases ---------------- */

const KIND_TEXT: Record<string, string> = {
  overdue: "Deadline passed",
  no_reply_recorded: "No reply recorded",
  due_soon: "Deadline soon",
  refused: "Refused",
  reappeared: "Back online",
};

export function FollowUpAssistant({ onApplied }: { onApplied?: () => void }) {
  const status = useAgentStatus();
  const [run, setRun] = useState<AgentRun | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function act(fn: () => Promise<AgentRun>) {
    setBusy(true);
    setError("");
    try {
      const r = await fn();
      setRun(r);
      setChosen(new Set((r.previews ?? []).map((p) => p.id)));
      if (r.status === "completed" && r.output.applied) onApplied?.();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const reminders: { link_id: string; kind: string; host: string; message: string }[] =
    run?.output.reminders ?? [];

  return (
    <section className="well stack" aria-labelledby="fu-h" style={{ marginBottom: "var(--space-xl)" }}>
      <div className="actions" style={{ justifyContent: "space-between" }}>
        <h2 id="fu-h">Deadlines and follow-ups</h2>
        <button className="btn btn--small" disabled={busy} onClick={() => act(api.runFollowUp)}>
          {busy ? "Checking" : run ? "Check again" : "Check deadlines"}
        </button>
      </div>
      {!run && (
        <p className="small">
          The assistant checks every link&apos;s deadline and prepares follow-up messages where a
          platform hasn&apos;t replied or has refused.
        </p>
      )}
      {run && reminders.length === 0 && <p className="small">Nothing needs attention right now.</p>}
      {reminders.length > 0 && (
        <ul className="rows">
          {reminders.map((r) => (
            <li key={`${r.link_id}-${r.kind}`}>
              <h3 className="small" style={{ fontSize: "var(--text-base)" }}>
                {r.host}
              </h3>
              <p className="small muted">{r.message}</p>
              <span className="badge" data-tone={r.kind === "due_soon" ? "neutral" : "warn"}>
                {KIND_TEXT[r.kind] ?? r.kind}
              </span>
            </li>
          ))}
        </ul>
      )}
      {run?.status === "awaiting_approval" && (run.previews?.length ?? 0) > 0 && (
        <div className="stack">
          <p className="small">
            <strong>Follow-up drafts.</strong> Tick the ones to keep. Nothing is sent; keeping one
            notes it on that link&apos;s history.
          </p>
          {run.previews!.map((p) => (
            <div key={p.id} className="stack">
              <label className="check">
                <input
                  type="checkbox"
                  checked={chosen.has(p.id)}
                  onChange={(e) => {
                    const next = new Set(chosen);
                    if (e.target.checked) next.add(p.id);
                    else next.delete(p.id);
                    setChosen(next);
                  }}
                />
                <span>Keep this draft</span>
              </label>
              <div className="notice">
                <strong>{p.subject}</strong>
                {"\n\n"}
                {p.body}
              </div>
              <SourceNote usedLlm={p.source === "llm"} status={status} />
            </div>
          ))}
          <div className="actions">
            <button
              className="btn btn--primary btn--small"
              disabled={busy}
              onClick={() => act(() => api.decideRun(run.id, "approve", [...chosen]))}
            >
              Keep selected drafts
            </button>
            <button
              className="btn btn--small"
              disabled={busy}
              onClick={() => act(() => api.decideRun(run.id, "reject"))}
            >
              Discard all
            </button>
          </div>
        </div>
      )}
      {run?.status === "completed" && (run.previews?.length ?? 0) > 0 && (
        <div className="stack">
          <p className="small">
            <strong>Kept drafts.</strong> Copy and send them yourself.
          </p>
          {run.previews!.map((p) => (
            <div key={p.id} className="notice">
              <strong>{p.subject}</strong>
              {"\n\n"}
              {p.body}
            </div>
          ))}
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  );
}

/* ---------------- Explain a match ---------------- */

export function MatchExplainer({ matchId }: { matchId: string }) {
  const [run, setRun] = useState<AgentRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!run) {
    return (
      <div>
        <button
          className="btn btn--ghost btn--small"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              setRun(await api.explainMatch(matchId));
            } catch (e) {
              setError(errorText(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Explaining" : "Explain this match"}
        </button>
        {error && <p className="error">{error}</p>}
      </div>
    );
  }
  const o = run.output;
  return (
    <div className="well stack small">
      <p>{o.summary}</p>
      <div>
        <strong>Worth gathering</strong>
        <ul style={{ margin: "var(--space-2xs) 0 0", paddingLeft: "1.2rem" }}>
          {(o.missing_evidence as string[]).map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      </div>
      <p>
        <strong>Next step:</strong> {o.next_step}
      </p>
      <p className="muted">{o.disclaimer}</p>
    </div>
  );
}

/* ---------------- Plan re-checks ---------------- */

export function RecheckPlanner({ onQueued }: { onQueued: () => void }) {
  const [run, setRun] = useState<AgentRun | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function act(fn: () => Promise<AgentRun>) {
    setBusy(true);
    setError("");
    try {
      const r = await fn();
      setRun(r);
      setChosen(new Set(((r.output.plan ?? []) as { id: string }[]).map((p) => p.id)));
      if (r.status === "completed" && (r.output.job_ids ?? []).length) onQueued();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const plan: { id: string; url: string; reason: string }[] = run?.output.plan ?? [];
  const skipped: { url: string; why: string }[] = run?.output.skipped ?? [];

  return (
    <div className="stack">
      <div>
        <button className="btn btn--small" disabled={busy} onClick={() => act(() => api.planDiscovery())}>
          {busy ? "Planning" : "Plan re-checks of known pages"}
        </button>
      </div>
      {run && (
        <div className="well stack small">
          {run.status === "awaiting_approval" ? (
            <>
              <p>
                <strong>Proposed checks.</strong> Nivra will visit these pages only if you approve.
              </p>
              {plan.map((p) => (
                <label key={p.id} className="check">
                  <input
                    type="checkbox"
                    checked={chosen.has(p.id)}
                    onChange={(e) => {
                      const next = new Set(chosen);
                      if (e.target.checked) next.add(p.id);
                      else next.delete(p.id);
                      setChosen(next);
                    }}
                  />
                  <span>
                    {p.url}
                    <span className="muted"> ({p.reason})</span>
                  </span>
                </label>
              ))}
              <div className="actions">
                <button
                  className="btn btn--primary btn--small"
                  disabled={busy || chosen.size === 0}
                  onClick={() => act(() => api.decideRun(run.id, "approve", [...chosen]))}
                >
                  Check selected pages
                </button>
                <button
                  className="btn btn--small"
                  disabled={busy}
                  onClick={() => act(() => api.decideRun(run.id, "reject"))}
                >
                  Cancel
                </button>
              </div>
            </>
          ) : (
            <p>
              {run.output.job_ids?.length
                ? `${run.output.job_ids.length} check(s) started. Results appear under Recent checks.`
                : (run.output.message ?? "Nothing was started.")}
            </p>
          )}
          {skipped.length > 0 && (
            <p className="muted">
              Skipped: {skipped.map((s) => `${s.url} (${s.why})`).join("; ")}
            </p>
          )}
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
