"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import {
  type EvidenceMeta,
  decryptBytes,
  decryptJson,
  encryptBytes,
  encryptJson,
  newLocker,
  openLocker,
  sha256Hex,
} from "@/lib/evidenceCrypto";
import { CATEGORY_LABEL } from "@/lib/notices";
import type { Complaint, EvidenceItemRaw, EvidenceKind, NivraCase } from "@/lib/types";

// Evidence locker (section 18.6). Encryption happens in this browser; the
// server only stores ciphertext. Nothing here is ever readable by Nivra.

const MAX_FILE = 7 * 1024 * 1024;
const KIND_LABEL: Record<EvidenceKind, string> = {
  screenshot: "Screenshot",
  file: "Other file",
  note: "Note",
  account: "Uploader's account",
  message: "Message or threat",
};

// Kept in memory for this page only (cleared by Lock, closing the tab or Quick exit).
let sessionKey: CryptoKey | null = null;

interface Item extends EvidenceItemRaw {
  meta: EvidenceMeta | null;
}

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "Something went wrong. Please try again.";

export default function EvidenceLocker({
  c,
  complaints,
  onChanged,
}: {
  c: NivraCase;
  complaints: Complaint[];
  onChanged?: () => void;
}) {
  const [state, setState] = useState<"loading" | "new" | "locked" | "open">("loading");
  const [locker, setLocker] = useState<{ salt: string; key_check: string } | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [pass, setPass] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadItems = useCallback(async () => {
    if (!sessionKey) return;
    const raw = await api.listEvidence(c.id);
    const out: Item[] = [];
    for (const r of raw) {
      let meta: EvidenceMeta | null = null;
      try {
        meta = await decryptJson<EvidenceMeta>(sessionKey, r.enc_meta);
      } catch {
        meta = null;
      }
      out.push({ ...r, meta });
    }
    setItems(out);
  }, [c.id]);

  useEffect(() => {
    api
      .getLocker()
      .then(async (l) => {
        if (!l.initialized) return setState("new");
        setLocker({ salt: l.salt, key_check: l.key_check });
        if (sessionKey) {
          setState("open");
          await loadItems();
        } else setState("locked");
      })
      .catch((e) => setError(errorText(e)));
  }, [loadItems]);

  async function setup(e: React.FormEvent) {
    e.preventDefault();
    if (pass.length < 8) return setError("Use your passphrase (at least 8 characters).");
    setBusy(true);
    setError("");
    try {
      const { salt, keyCheck, key } = await newLocker(pass);
      await api.createLocker(salt, keyCheck);
      sessionKey = key;
      setPass("");
      setLocker({ salt, key_check: keyCheck });
      setState("open");
      await loadItems();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function unlock(e: React.FormEvent) {
    e.preventDefault();
    if (!locker) return;
    setBusy(true);
    setError("");
    const key = await openLocker(pass, locker.salt, locker.key_check);
    setBusy(false);
    if (!key) return setError("That passphrase doesn't open this locker.");
    sessionKey = key;
    setPass("");
    setState("open");
    await loadItems().catch((err) => setError(errorText(err)));
  }

  function lock() {
    sessionKey = null;
    setItems([]);
    setState("locked");
  }

  return (
    <section className="section stack" aria-labelledby="ev-h">
      <div className="actions" style={{ justifyContent: "space-between" }}>
        <h2 id="ev-h">Evidence locker</h2>
        {state === "open" && (
          <button className="btn btn--small" onClick={lock}>
            Lock
          </button>
        )}
      </div>
      <p className="small">
        Keep screenshots, the uploader&apos;s account and messages in one place for police or a
        lawyer. Everything is encrypted on this device with your passphrase before it&apos;s
        saved. Nivra can&apos;t read it, and can&apos;t recover it if you forget your passphrase.
      </p>

      {state === "new" && (
        <form onSubmit={setup} className="well stack" style={{ maxWidth: "32rem" }}>
          <label htmlFor="ev-new">Your passphrase, to set up the locker</label>
          <input id="ev-new" type="password" className="input" value={pass}
            onChange={(e) => setPass(e.target.value)} autoComplete="current-password" />
          <span className="hint">Use the same passphrase you open your account with.</span>
          <div>
            <button className="btn btn--primary btn--small" disabled={busy}>
              {busy ? "Setting up" : "Set up my locker"}
            </button>
          </div>
        </form>
      )}

      {state === "locked" && (
        <form onSubmit={unlock} className="well stack" style={{ maxWidth: "32rem" }}>
          <label htmlFor="ev-pass">Passphrase</label>
          <input id="ev-pass" type="password" className="input" value={pass}
            onChange={(e) => setPass(e.target.value)} autoComplete="current-password" />
          <div>
            <button className="btn btn--primary btn--small" disabled={busy || !pass}>
              {busy ? "Opening" : "Open locker"}
            </button>
          </div>
        </form>
      )}

      {state === "open" && sessionKey && (
        <>
          <AddEvidence c={c} onAdded={async () => { await loadItems(); onChanged?.(); }} />
          {items.length === 0 ? (
            <p className="well">Nothing saved yet.</p>
          ) : (
            <ul className="links">
              {items.map((it) => (
                <EvidenceRow key={it.id} item={it} c={c} onDeleted={loadItems} />
              ))}
            </ul>
          )}
          <div>
            <button className="btn btn--small" onClick={() => downloadReport(c, items, complaints)}>
              Download evidence report
            </button>
            <p className="hint" style={{ marginTop: "var(--space-xs)" }}>
              A summary file with your links, their history, complaints and a fingerprint (SHA-256)
              of each saved file, made on this device. It doesn&apos;t include the images.
            </p>
          </div>
        </>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  );
}

function AddEvidence({ c, onAdded }: { c: NivraCase; onAdded: () => Promise<void> }) {
  const [kind, setKind] = useState<EvidenceKind>("screenshot");
  const [linkId, setLinkId] = useState("");
  const [caption, setCaption] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const isFile = kind === "screenshot" || kind === "file";

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!sessionKey) return;
    if (isFile && !file) return setError("Choose a file.");
    if (!isFile && !text.trim()) return setError("Write something to save.");
    if (file && file.size > MAX_FILE) return setError("That file is larger than 7 MB.");
    setBusy(true);
    setError("");
    try {
      const meta: EvidenceMeta = { caption: caption.trim() };
      let blob: string | undefined;
      if (isFile && file) {
        const bytes = new Uint8Array(await file.arrayBuffer());
        Object.assign(meta, { filename: file.name, mime: file.type, size: file.size,
          sha256: await sha256Hex(bytes) });
        blob = await encryptBytes(sessionKey, bytes);
      } else {
        meta.text = text.trim();
      }
      await api.addEvidence(c.id, { kind, link_id: linkId || null,
        enc_meta: await encryptJson(sessionKey, meta), blob });
      setCaption("");
      setText("");
      setFile(null);
      (e.target as HTMLFormElement).reset();
      await onAdded();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="well stack">
      <h3>Add evidence</h3>
      <div className="actions">
        <select className="input" style={{ width: "auto" }} aria-label="What is it"
          value={kind} onChange={(e) => setKind(e.target.value as EvidenceKind)}>
          {(Object.keys(KIND_LABEL) as EvidenceKind[]).map((k) => (
            <option key={k} value={k}>{KIND_LABEL[k]}</option>
          ))}
        </select>
        <select className="input" style={{ width: "auto" }} aria-label="Which link"
          value={linkId} onChange={(e) => setLinkId(e.target.value)}>
          <option value="">Whole case</option>
          {c.links.map((l) => (
            <option key={l.id} value={l.id}>{l.host}</option>
          ))}
        </select>
      </div>
      {isFile ? (
        <input type="file" aria-label="File" accept={kind === "screenshot" ? "image/*" : undefined}
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      ) : (
        <textarea className="textarea" style={{ minHeight: "5rem" }} aria-label="Details"
          placeholder={kind === "account" ? "Username or profile link of who posted it" : "Write it down"}
          value={text} onChange={(e) => setText(e.target.value)} />
      )}
      <input className="input" placeholder="Short description (optional, also encrypted)"
        value={caption} maxLength={200} onChange={(e) => setCaption(e.target.value)} />
      {error && <p className="error">{error}</p>}
      <div>
        <button className="btn btn--primary btn--small" disabled={busy}>
          {busy ? "Encrypting" : "Encrypt and save"}
        </button>
      </div>
    </form>
  );
}

function EvidenceRow({ item, c, onDeleted }: { item: Item; c: NivraCase; onDeleted: () => Promise<void> }) {
  const [view, setView] = useState<string | null>(null); // object URL for images
  const [reveal, setReveal] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState("");
  const host = c.links.find((l) => l.id === item.link_id)?.host;

  useEffect(() => () => { if (view) URL.revokeObjectURL(view); }, [view]);

  async function fileBlob(): Promise<Blob | null> {
    if (!sessionKey) return null;
    const { blob } = await api.getEvidenceBlob(item.id);
    const bytes = await decryptBytes(sessionKey, blob);
    return new Blob([bytes as BlobPart], { type: item.meta?.mime || "application/octet-stream" });
  }

  async function open() {
    try {
      const b = await fileBlob();
      if (b) setView(URL.createObjectURL(b));
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function download() {
    try {
      const b = await fileBlob();
      if (!b) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(b);
      a.download = item.meta?.filename || `evidence-${item.id}`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <li className="link-item">
      <div className="stack" style={{ paddingBlock: "var(--space-md)" }}>
        <div className="actions" style={{ justifyContent: "space-between" }}>
          <span className="small">
            <strong>{KIND_LABEL[item.kind]}</strong>
            {item.meta?.caption ? `: ${item.meta.caption}` : ""}
            <span className="muted">
              {" "}
              {host ? `(${host}) ` : ""}
              {new Date(item.created_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
            </span>
          </span>
          {!item.meta && <span className="badge" data-tone="warn">Can&apos;t decrypt</span>}
        </div>
        {item.meta?.text && <div className="notice">{item.meta.text}</div>}
        {view && item.meta?.mime?.startsWith("image/") && (
          <div className="preview-wrap">
            {/* eslint-disable-next-line @next/next/no-img-element -- decrypted local blob */}
            <img src={view} alt="Saved evidence" className="preview" data-reveal={reveal} />
            <button className="btn btn--small" onClick={() => setReveal((r) => !r)}>
              {reveal ? "Blur" : "Show"}
            </button>
          </div>
        )}
        <div className="actions">
          {item.has_blob && item.meta?.mime?.startsWith("image/") && !view && (
            <button className="btn btn--small" onClick={open}>View (blurred)</button>
          )}
          {item.has_blob && <button className="btn btn--small" onClick={download}>Download</button>}
          {!confirm ? (
            <button className="btn btn--ghost btn--small" onClick={() => setConfirm(true)}>Delete</button>
          ) : (
            <>
              <button className="btn btn--danger btn--small"
                onClick={async () => { await api.deleteEvidence(item.id); await onDeleted(); }}>
                Delete permanently
              </button>
              <button className="btn btn--small" onClick={() => setConfirm(false)}>Keep</button>
            </>
          )}
        </div>
        {error && <p className="error">{error}</p>}
      </div>
    </li>
  );
}

const esc = (s: string) =>
  s.replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]!);

/** Builds a self-contained HTML report on this device and downloads it. */
function downloadReport(c: NivraCase, items: Item[], complaints: Complaint[]) {
  const fmt = (iso: string) => new Date(iso).toLocaleString("en-IN");
  const links = c.links.map((l) => `
    <h3>${esc(l.url)}</h3>
    <ul>${l.events.map((e) => `<li>${esc(fmt(e.at))}: ${esc(e.note ?? e.status)}</li>`).join("")}</ul>
    ${complaints.filter((x) => x.link_id === l.id).map((x) => `
      <p><b>Complaint</b> (${esc(x.status_label)}${x.reference ? `, ref. ${esc(x.reference)}` : ""})</p>
      <ul>${x.events.map((e) => `<li>${esc(fmt(e.at))}: ${esc(e.note ?? e.status)}</li>`).join("")}</ul>`).join("")}`).join("");
  const ev = items.map((i) => `
    <tr><td>${esc(fmt(i.created_at))}</td><td>${esc(KIND_LABEL[i.kind])}</td>
    <td>${esc(c.links.find((l) => l.id === i.link_id)?.url ?? "Whole case")}</td>
    <td>${esc(i.meta?.caption ?? "")}${i.meta?.text ? `<br>${esc(i.meta.text)}` : ""}</td>
    <td>${esc(i.meta?.filename ?? "")}</td><td style="font-family:monospace;font-size:11px">${esc(i.meta?.sha256 ?? "")}</td></tr>`).join("");
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>Evidence report</title>
  <style>body{font:14px/1.5 system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1b2b20}
  table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:6px;text-align:left;vertical-align:top}</style></head><body>
  <h1>Evidence report</h1>
  <p>Generated ${esc(new Date().toLocaleString("en-IN"))} by Nivra, on the user's own device.
  Case type: ${esc(CATEGORY_LABEL[c.category])}. Opened ${esc(fmt(c.created_at))}.</p>
  <h2>Links and what happened</h2>${links || "<p>No links.</p>"}
  <h2>Saved evidence</h2>
  <p>SHA-256 is a fingerprint of each original file: if the file is changed in any way, its fingerprint changes.</p>
  <table><tr><th>Saved</th><th>Type</th><th>Link</th><th>Description</th><th>File</th><th>SHA-256</th></tr>${ev}</table>
  </body></html>`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([html], { type: "text/html" }));
  a.download = `nivra-evidence-report-${new Date().toISOString().slice(0, 10)}.html`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
