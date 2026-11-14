"use client";

import Link from "next/link";
import { useState } from "react";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";

// Open an existing anonymous account (Nivra ID + passphrase) or create one.
// Used by /case and /protect.

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "Something went wrong. Please try again.";

export default function AccountGate({
  title = "Open your account",
  intro = "Enter the Nivra ID you were given and your passphrase.",
  allowCreate = false,
  onOpen,
}: {
  title?: string;
  intro?: string;
  allowCreate?: boolean;
  onOpen: () => void;
}) {
  const [mode, setMode] = useState<"open" | "create" | "created">("open");
  const [id, setId] = useState("");
  const [pass, setPass] = useState("");
  const [pass2, setPass2] = useState("");
  const [newId, setNewId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function open(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.login(id, pass);
      setPass("");
      onOpen();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (pass.length < 8) return setError("Use at least 8 characters for your passphrase.");
    if (pass !== pass2) return setError("The two passphrases don't match.");
    setBusy(true);
    setError("");
    try {
      const { account_code } = await api.register(pass);
      setPass("");
      setPass2("");
      setNewId(account_code);
      setMode("created");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  if (mode === "created") {
    return (
      <div className="container narrow section stack-lg">
        <h1>Your account is ready</h1>
        <div className="slip">
          <p className="label">Your Nivra ID. Write it down somewhere safe.</p>
          <p className="slip__id num">{newId}</p>
        </div>
        <p>You&apos;ll need this ID and your passphrase to come back. We can&apos;t recover them.</p>
        <div className="actions">
          <button className="btn btn--primary" onClick={onOpen}>
            Continue
          </button>
        </div>
      </div>
    );
  }

  if (mode === "create") {
    return (
      <div className="container narrow section">
        <h1>Create an account</h1>
        <p style={{ margin: "var(--space-sm) 0 var(--space-xl)" }}>
          No email or name needed. You&apos;ll get a Nivra ID, and this passphrase opens it.
        </p>
        <form onSubmit={create}>
          <div className="field">
            <label htmlFor="np1">Passphrase</label>
            <input
              id="np1"
              type="password"
              className="input"
              value={pass}
              onChange={(e) => setPass(e.target.value)}
              autoComplete="new-password"
            />
            <span className="hint">At least 8 characters. A short sentence is easy to remember.</span>
          </div>
          <div className="field">
            <label htmlFor="np2">Type it again</label>
            <input
              id="np2"
              type="password"
              className="input"
              value={pass2}
              onChange={(e) => setPass2(e.target.value)}
              autoComplete="new-password"
            />
          </div>
          {error && <p className="error">{error}</p>}
          <div className="actions" style={{ marginTop: "var(--space-lg)" }}>
            <button className="btn btn--primary" disabled={busy}>
              {busy ? "Creating" : "Create account"}
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => {
                setError("");
                setMode("open");
              }}
            >
              I already have one
            </button>
          </div>
        </form>
      </div>
    );
  }

  return (
    <div className="container narrow section">
      <h1>{title}</h1>
      <p style={{ margin: "var(--space-sm) 0 var(--space-xl)" }}>{intro}</p>
      <form onSubmit={open}>
        <div className="field">
          <label htmlFor="cid">Nivra ID</label>
          <input
            id="cid"
            className="input num"
            placeholder="NV-XXXX-XXXX"
            value={id}
            onChange={(e) => setId(e.target.value)}
            autoComplete="username"
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
            {busy ? "Checking" : "Open account"}
          </button>
          {allowCreate ? (
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => {
                setError("");
                setMode("create");
              }}
            >
              Create an account
            </button>
          ) : (
            <Link href="/start" className="btn btn--ghost">
              Start a new case instead
            </Link>
          )}
        </div>
      </form>
    </div>
  );
}
