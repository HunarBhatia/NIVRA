"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import AccountGate from "@/components/AccountGate";
import DiscoveryPanel from "./DiscoveryPanel";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import { UnreadableImage, fingerprintFile, type Fingerprints } from "@/lib/fingerprint";
import { CYBERCRIME_URL, TAKE_IT_DOWN_URL } from "@/lib/platforms";
import type { MatchCheck, MatchClass, ProtectedImage } from "@/lib/types";

// Protect images (phase 3). The user picks an image ON THEIR DEVICE; the
// browser computes its fingerprints (SHA-256, pHash, optional AI embedding)
// and only those are sent to Nivra (decision D13). See PROJECT_DETAILS.txt 15.

type View = "loading" | "locked" | "open" | "offline";

const errorText = (e: unknown) =>
  e instanceof ApiError || e instanceof UnreadableImage
    ? e.message
    : "Something went wrong. Please try again.";

const dateFmt = (iso: string) =>
  new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

export default function ProtectView() {
  const [view, setView] = useState<View>("loading");
  const [images, setImages] = useState<ProtectedImage[]>([]);
  const [error, setError] = useState("");
  const [adding, setAdding] = useState(false);
  const [toReview, setToReview] = useState(0);

  const load = useCallback(async () => {
    try {
      const me = await api.getMe();
      if (!me) return setView("locked");
      setImages(await api.listImages());
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
        <button className="btn btn--primary" onClick={() => load()}>
          Try again
        </button>
      </div>
    );
  }
  if (view === "locked") {
    return (
      <AccountGate
        title="Protect your images"
        intro="Open your Nivra account, or create one. No email or name needed."
        allowCreate
        onOpen={() => load()}
      />
    );
  }

  const replace = (img: ProtectedImage) =>
    setImages((list) => list.map((i) => (i.id === img.id ? img : i)));

  return (
    <div className="container">
      <div className="dash-head">
        <div>
          <h1>Protected images</h1>
          <p style={{ marginTop: "var(--space-sm)" }}>
            Nivra keeps fingerprints of images you want to watch for. The images themselves never
            leave this device.
          </p>
          <div className="tally">
            <div>
              <strong className="num">{images.length}</strong>
              <span className="small muted">protected</span>
            </div>
            <div>
              <strong className="num">{images.filter((i) => i.status === "active").length}</strong>
              <span className="small muted">active</span>
            </div>
            <div>
              <strong className="num">{toReview}</strong>
              <span className="small muted">matches to review</span>
            </div>
          </div>
        </div>
        <div className="well small stack">
          <p>
            <strong>What works today:</strong> Nivra checks any page you point it to, and you can
            check a saved copy against your images.
          </p>
          <p className="muted">
            Nivra doesn&apos;t search the whole web on its own yet. Scheduled re-checks come later.
          </p>
        </div>
      </div>

      {!adding ? (
        <div className="actions" style={{ marginBottom: "var(--space-xl)" }}>
          <button className="btn btn--primary" onClick={() => setAdding(true)}>
            Protect a new image
          </button>
        </div>
      ) : (
        <RegisterFlow
          onDone={(img) => {
            setImages((list) => [...list, img]);
            setAdding(false);
          }}
          onCancel={() => setAdding(false)}
        />
      )}

      <section aria-labelledby="list-h" style={{ marginBottom: "var(--space-2xl)" }}>
        <h2 id="list-h" style={{ marginBottom: "var(--space-md)" }}>
          Your images
        </h2>
        {images.length === 0 ? (
          <p className="well">No protected images yet.</p>
        ) : (
          <ul className="links">
            {images.map((img, i) => (
              <ImageRow
                key={img.id}
                img={img}
                index={i}
                onChange={replace}
                onRemoved={() => setImages((list) => list.filter((x) => x.id !== img.id))}
              />
            ))}
          </ul>
        )}
      </section>

      {images.length > 0 && <DiscoveryPanel onMatchesChanged={setToReview} />}
      {images.length > 0 && <CheckCopy />}
    </div>
  );
}

/* ---------------- Register a new image ---------------- */

type Step = "consent" | "minor" | "choose" | "working";

function RegisterFlow({
  onDone,
  onCancel,
}: {
  onDone: (img: ProtectedImage) => void;
  onCancel: () => void;
}) {
  const [step, setStep] = useState<Step>("consent");
  const [adult, setAdult] = useState<"yes" | "no" | "">("");
  const [authorised, setAuthorised] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [label, setLabel] = useState("");
  const [withAi, setWithAi] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");

  function nextFromConsent() {
    if (!adult) return setError("Please answer the first question.");
    if (adult === "no") return setStep("minor");
    if (!authorised) return setError("Please confirm the second statement to continue.");
    setError("");
    setStep("choose");
  }

  async function protect() {
    if (!file) return setError("Choose an image first.");
    setError("");
    setStep("working");
    try {
      const fp = await fingerprintFile(file, {
        embedding: withAi,
        onProgress: (p) =>
          setProgress(
            p.status === "progress" && p.progress !== undefined
              ? `Downloading the AI model (${Math.round(p.progress)}%)`
              : p.status === "initiate" || p.status === "download"
                ? "Downloading the AI model"
                : p.status === "done" || p.status === "ready"
                  ? "Preparing the AI model"
                  : p.status,
          ),
      });
      setFile(null); // drop our reference to the image as soon as we're done
      setProgress("Saving fingerprints");
      onDone(await api.registerImage({ label, fingerprints: fp }));
    } catch (e) {
      setError(errorText(e));
      setStep("choose");
    }
  }

  return (
    <section className="well stack-lg" style={{ marginBottom: "var(--space-xl)" }}>
      {step === "consent" && (
        <>
          <h2>Before you add an image</h2>
          <fieldset className="choices">
            <legend className="label" style={{ marginBottom: "var(--space-sm)" }}>
              Was the person in this image 18 or older when it was taken?
            </legend>
            <label className="choice">
              <input type="radio" name="adult" checked={adult === "yes"} onChange={() => setAdult("yes")} />
              <span>
                <strong>Yes, they were 18 or older</strong>
              </span>
            </label>
            <label className="choice">
              <input type="radio" name="adult" checked={adult === "no"} onChange={() => setAdult("no")} />
              <span>
                <strong>No, or I&apos;m not sure</strong>
              </span>
            </label>
          </fieldset>
          <label className="check">
            <input
              type="checkbox"
              checked={authorised}
              onChange={(e) => setAuthorised(e.target.checked)}
            />
            <span>This image is of me, or I have the person&apos;s permission to protect it.</span>
          </label>
          {error && <p className="error">{error}</p>}
          <div className="actions">
            <button className="btn btn--primary" onClick={nextFromConsent}>
              Continue
            </button>
            <button className="btn btn--ghost" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </>
      )}

      {step === "minor" && (
        <>
          <h2>Please use these services instead</h2>
          <p>
            Nivra doesn&apos;t handle images of anyone under 18. Take It Down can block them on
            partner platforms without the image being sent, and the police can act with powers we
            don&apos;t have.
          </p>
          <div className="actions">
            <a className="btn btn--primary" href={TAKE_IT_DOWN_URL} target="_blank" rel="noreferrer">
              Open Take It Down
            </a>
            <a className="btn" href={CYBERCRIME_URL} target="_blank" rel="noreferrer">
              Report at cybercrime.gov.in
            </a>
            <a className="btn" href="tel:1930">
              Call 1930
            </a>
          </div>
          <button className="btn btn--ghost" onClick={onCancel}>
            Close
          </button>
        </>
      )}

      {step === "choose" && (
        <>
          <h2>Choose the image</h2>
          <p className="small">
            Your device creates the fingerprints. Only those are sent to Nivra; the image stays
            here.
          </p>
          <FilePicker file={file} onFile={setFile} id="protect-file" />
          <div className="field" style={{ maxWidth: "28rem" }}>
            <label htmlFor="img-label">A name only you&apos;ll recognise (optional)</label>
            <input
              id="img-label"
              className="input"
              value={label}
              maxLength={80}
              placeholder="e.g. Photo 1"
              onChange={(e) => setLabel(e.target.value)}
              autoComplete="off"
            />
            <span className="hint">Avoid describing the image. This name is stored on our server.</span>
          </div>
          <label className="check">
            <input type="checkbox" checked={withAi} onChange={(e) => setWithAi(e.target.checked)} />
            <span>
              Also create an AI similarity fingerprint. It catches edited or cropped copies.{" "}
              <span className="muted">
                One-time download of about 90 MB from Hugging Face; it runs on this device.
              </span>
            </span>
          </label>
          {error && <p className="error">{error}</p>}
          <div className="actions">
            <button className="btn btn--primary" onClick={protect} disabled={!file}>
              Create fingerprints
            </button>
            <button className="btn btn--ghost" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </>
      )}

      {step === "working" && (
        <>
          <h2>Creating fingerprints on this device</h2>
          <p aria-live="polite">{progress || "Starting"}</p>
          <p className="small muted">Please keep this page open.</p>
        </>
      )}
    </section>
  );
}

/* ---------------- File picker with a blurred preview ---------------- */

function FilePicker({
  file,
  onFile,
  id,
}: {
  file: File | null;
  onFile: (f: File | null) => void;
  id: string;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [reveal, setReveal] = useState(false);

  useEffect(() => {
    if (!file) return;
    const u = URL.createObjectURL(file);
    // Showing a local preview of the chosen file (never uploaded).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setUrl(u);
    setReveal(false);
    return () => {
      URL.revokeObjectURL(u);
      setUrl(null);
    };
  }, [file]);

  return (
    <div className="field">
      <label htmlFor={id}>Image</label>
      <input
        id={id}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif,image/avif"
        onChange={(e) => onFile(e.target.files?.[0] ?? null)}
      />
      {url && (
        <div className="preview-wrap">
          {/* eslint-disable-next-line @next/next/no-img-element -- local blob preview, never uploaded */}
          <img src={url} alt="Your chosen image" className="preview" data-reveal={reveal} />
          <button type="button" className="btn btn--small" onClick={() => setReveal((r) => !r)}>
            {reveal ? "Blur preview" : "Show preview"}
          </button>
        </div>
      )}
    </div>
  );
}

/* ---------------- One protected image ---------------- */

const FP_LABEL: Record<string, string> = {
  sha256: "Exact-file fingerprint",
  phash: "Visual fingerprint",
  embedding: "AI similarity fingerprint",
};

function ImageRow({
  img,
  index,
  onChange,
  onRemoved,
}: {
  img: ProtectedImage;
  index: number;
  onChange: (img: ProtectedImage) => void;
  onRemoved: () => void;
}) {
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [addingAi, setAddingAi] = useState(false);
  const [aiFile, setAiFile] = useState<File | null>(null);
  const [aiProgress, setAiProgress] = useState("");
  const hasAi = img.fingerprints.some((f) => f.kind === "embedding");

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

  const addAi = () =>
    run(async () => {
      if (!aiFile) return;
      setAiProgress("Starting");
      const fp = await fingerprintFile(aiFile, {
        embedding: true,
        onProgress: (p) =>
          setAiProgress(
            p.status === "progress" && p.progress !== undefined
              ? `Downloading the AI model (${Math.round(p.progress)}%)`
              : p.status,
          ),
      });
      setAiFile(null);
      if (!fp.embedding) return;
      onChange(await api.setImageEmbedding(img.id, fp.embedding));
      setAddingAi(false);
      setAiProgress("");
    }).finally(() => setAiProgress(""));

  return (
    <li className="link-item">
      <details>
        <summary>
          <span style={{ minWidth: 0 }}>
            <span className="link-item__url" style={{ display: "block" }}>
              {img.label || `Image ${index + 1}`}
            </span>
            <span className="small muted">Added {dateFmt(img.created_at)}</span>
          </span>
          <span className="badge" data-tone={img.status === "active" ? "good" : "neutral"}>
            {img.status === "active" ? "Active" : "Paused"}
          </span>
        </summary>
        <div className="stack" style={{ paddingBottom: "var(--space-xl)" }}>
          <ul className="timeline">
            {(["sha256", "phash", "embedding"] as const).map((k) => {
              const fp = img.fingerprints.find((f) => f.kind === k);
              return (
                <li key={k}>
                  <span>{FP_LABEL[k]}: </span>
                  <span className="muted">
                    {fp ? `saved (${fp.algorithm})` : "not added"}
                  </span>
                </li>
              );
            })}
          </ul>

          {!hasAi && !addingAi && (
            <div>
              <button className="btn btn--small" onClick={() => setAddingAi(true)}>
                Add AI similarity fingerprint
              </button>
            </div>
          )}
          {addingAi && (
            <div className="well stack">
              <p className="small">
                We don&apos;t keep your image, so choose the same image again. The AI model
                (about 90 MB, once) runs on this device.
              </p>
              <FilePicker file={aiFile} onFile={setAiFile} id={`ai-${img.id}`} />
              {aiProgress && <p aria-live="polite">{aiProgress}</p>}
              <div className="actions">
                <button className="btn btn--primary btn--small" disabled={!aiFile || busy} onClick={addAi}>
                  Create it
                </button>
                <button className="btn btn--ghost btn--small" onClick={() => setAddingAi(false)}>
                  Cancel
                </button>
              </div>
            </div>
          )}

          <div className="actions">
            <button
              className="btn btn--small"
              disabled={busy}
              onClick={() =>
                run(async () =>
                  onChange(
                    await api.updateImage(img.id, {
                      status: img.status === "active" ? "paused" : "active",
                    }),
                  ),
                )
              }
            >
              {img.status === "active" ? "Pause monitoring" : "Resume monitoring"}
            </button>
            {!confirm ? (
              <button className="btn btn--danger btn--small" onClick={() => setConfirm(true)}>
                Remove protection
              </button>
            ) : (
              <>
                <button
                  className="btn btn--danger btn--small"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      await api.revokeImage(img.id);
                      onRemoved();
                    })
                  }
                >
                  Yes, delete its fingerprints
                </button>
                <button className="btn btn--small" onClick={() => setConfirm(false)}>
                  Keep it
                </button>
              </>
            )}
          </div>
          {error && <p className="error">{error}</p>}
        </div>
      </details>
    </li>
  );
}

/* ---------------- Check a copy ---------------- */

const CLASS_TEXT: Record<MatchClass, { label: string; tone: string }> = {
  exact: { label: "Exact same file", tone: "warn" },
  high: { label: "Very likely the same image", tone: "warn" },
  possible: { label: "Possibly the same image", tone: "neutral" },
  none: { label: "Not a match", tone: "good" },
};

function CheckCopy() {
  const [file, setFile] = useState<File | null>(null);
  const [withAi, setWithAi] = useState(false);
  const [result, setResult] = useState<MatchCheck | null>(null);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const busyRef = useRef(false);

  async function check() {
    if (!file || busyRef.current) return;
    busyRef.current = true;
    setError("");
    setResult(null);
    try {
      const fp: Fingerprints = await fingerprintFile(file, {
        embedding: withAi,
        onProgress: (p) =>
          setProgress(
            p.status === "progress" && p.progress !== undefined
              ? `Downloading the AI model (${Math.round(p.progress)}%)`
              : p.status,
          ),
      });
      setFile(null);
      setResult(await api.checkCopy(fp));
    } catch (e) {
      setError(errorText(e));
    } finally {
      busyRef.current = false;
      setProgress("");
    }
  }

  return (
    <section className="section stack" aria-labelledby="check-h">
      <h2 id="check-h">Check a copy you found</h2>
      <p>
        Saved a copy of an image you found online? Check it against your protected images. It is
        fingerprinted on this device and compared only with your own images.
      </p>
      <FilePicker file={file} onFile={setFile} id="check-file" />
      <label className="check">
        <input type="checkbox" checked={withAi} onChange={(e) => setWithAi(e.target.checked)} />
        <span>Use the AI similarity fingerprint too (uses the same one-time download).</span>
      </label>
      <div className="actions">
        <button className="btn btn--primary" disabled={!file || !!progress} onClick={check}>
          Check this copy
        </button>
      </div>
      {progress && <p aria-live="polite">{progress}</p>}
      {error && <p className="error">{error}</p>}
      {result && (
        <div className="stack">
          <ul className="rows" aria-live="polite">
            {result.results.map((r) => {
              const c = CLASS_TEXT[r.classification];
              return (
                <li key={r.image_id}>
                  <h3>{r.label || "Untitled image"}</h3>
                  <p className="small muted">
                    {r.sha256_equal
                      ? "Byte-for-byte the same file."
                      : `Visual difference ${r.phash_distance ?? "?"} of 64`}
                    {r.cosine !== null ? `; AI similarity ${r.cosine.toFixed(2)}` : ""}
                  </p>
                  <span className="badge" data-tone={c.tone}>
                    {c.label}
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="small muted">
            This is a suggestion based on fingerprints, not a decision. Only you can confirm
            whether it&apos;s your image. If it is, <Link href="/start">start a case</Link> with
            the link where you found it.
          </p>
        </div>
      )}
    </section>
  );
}
