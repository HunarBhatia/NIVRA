"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  addWatch,
  createCase,
  createDiscoveryJob,
  getDemoInfo,
  getMe,
  register,
  registerImage,
} from "@/lib/api";
import BitGrid from "@/components/motion/BitGrid";
import LiveScan from "@/components/scan/LiveScan";
import { UnreadableImage, fingerprintFile, type Fingerprints } from "@/lib/fingerprint";
import { CATEGORY_LABEL } from "@/lib/notices";
import { TAKE_IT_DOWN_URL, normaliseUrl, resolvePlatform, splitLinks } from "@/lib/platforms";
import type { Account, Category, DemoInfo, DiscoveryJob } from "@/lib/types";

// The "Start a case" wizard (blueprint 10.2). One decision per screen.

type Step = "safety" | "minor" | "what" | "photo" | "links" | "evidence" | "save" | "done";
const ORDER: Step[] = ["safety", "what", "photo", "links", "evidence", "save", "done"];

const CATEGORY_HINT: Record<Category, string> = {
  intimate: "A real photo or video of you, shared without your consent.",
  morphed: "An edited or AI-made image that uses your face or body.",
  impersonation: "An account pretending to be you, using your photos.",
};

const REVERSE_SEARCH = [
  { name: "Google Lens", url: "https://lens.google.com/" },
  { name: "TinEye", url: "https://tineye.com/" },
  { name: "Bing Visual Search", url: "https://www.bing.com/visualsearch" },
  { name: "Yandex Images", url: "https://yandex.com/images/" },
];

function parseLinks(text: string) {
  return splitLinks(text).map((raw) => ({ raw, url: normaliseUrl(raw) }));
}

export default function StartWizard() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("safety");
  const [under18, setUnder18] = useState<"no" | "yes" | "">("");
  const [category, setCategory] = useState<Category | "">("");
  const [selfTaken, setSelfTaken] = useState<"yes" | "no" | "unsure" | "">("");
  const [linkText, setLinkText] = useState("");
  const [evidenceDone, setEvidenceDone] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [pass1, setPass1] = useState("");
  const [pass2, setPass2] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [nivraId, setNivraId] = useState("");
  const [copied, setCopied] = useState(false);
  // Already logged in? Then the new case is added to that account and the
  // passphrase step is skipped.
  const [account, setAccount] = useState<Account | null>(null);
  // Photo step (section 22.4): fingerprinted HERE, the file never leaves.
  const [photoUrl, setPhotoUrl] = useState("");
  const [reveal, setReveal] = useState(false);
  const [prints, setPrints] = useState<Fingerprints | null>(null);
  const [fpBusy, setFpBusy] = useState(false);
  const [authorised, setAuthorised] = useState(false);
  const [over, setOver] = useState(false);
  const [checkNow, setCheckNow] = useState(true);
  const [watch, setWatch] = useState(false);
  const [jobIds, setJobIds] = useState<string[]>([]);
  const [finishedJobs, setFinishedJobs] = useState<DiscoveryJob[] | null>(null);
  // Bundled demo sites (section 23), shown only when the server enables them.
  const [demo, setDemo] = useState<DemoInfo | null>(null);
  const [scanNotes, setScanNotes] = useState<string[]>([]);

  useEffect(() => {
    getMe()
      .then(setAccount)
      .catch(() => setAccount(null));
    getDemoInfo()
      .then((d) => setDemo(d.enabled ? d : null))
      .catch(() => {});
  }, []);

  async function loadDemoPhoto() {
    if (!demo?.photo) return;
    const blob = await (await fetch(demo.photo)).blob();
    await choosePhoto(new File([blob], "demo-photo.jpg", { type: blob.type || "image/jpeg" }));
  }

  const parsed = useMemo(() => parseLinks(linkText), [linkText]);
  const validUrls = parsed.filter((p) => p.url).map((p) => p.url as string);
  const invalid = parsed.filter((p) => !p.url);

  const stepIndex = ORDER.indexOf(step === "minor" ? "safety" : step);

  // Each new step starts at the top of the page.
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [step]);

  function go(next: Step) {
    setError("");
    setStep(next);
  }

  function nextFromSafety() {
    if (!under18) return setError("Please choose an answer to continue.");
    go(under18 === "yes" ? "minor" : "what");
  }

  function nextFromWhat() {
    if (!category) return setError("Please choose what happened.");
    go("photo");
  }

  async function choosePhoto(file: File | undefined) {
    if (!file) return;
    if (!file.type.startsWith("image/")) return setError("Please choose an image file.");
    setError("");
    setPrints(null);
    setReveal(false);
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    setPhotoUrl(URL.createObjectURL(file));
    setFpBusy(true);
    try {
      setPrints(await fingerprintFile(file, { embedding: false }));
    } catch (e) {
      setError(e instanceof UnreadableImage ? "That image couldn't be read. Try a JPG or PNG." : "Couldn't fingerprint that image.");
    } finally {
      setFpBusy(false);
    }
  }

  function nextFromPhoto() {
    if (prints && !authorised) return setError("Please confirm you are the person in the photo or are acting for them.");
    go("links");
  }

  function skipPhoto() {
    setPrints(null);
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    setPhotoUrl("");
    go("links");
  }

  function nextFromLinks() {
    if (validUrls.length === 0) return setError("Add at least one link, like instagram.com/p/...");
    go("evidence");
  }

  async function save() {
    if (!account) {
      if (pass1.length < 8) return setError("Use at least 8 characters for your passphrase.");
      if (pass1 !== pass2) return setError("The two passphrases don't match.");
    }
    setBusy(true);
    try {
      let code = account?.account_code ?? "";
      if (!account) {
        code = (await register(pass1)).account_code;
        setPass1("");
        setPass2("");
      }
      if (prints) {
        try {
          await registerImage({ label: "Photo from my case", fingerprints: prints });
        } catch (e) {
          // Already protected (same photo added before) is fine.
          if (!(e instanceof ApiError && e.status === 409)) throw e;
        }
      }
      const created = await createCase({
        category: category as Category,
        self_taken: selfTaken === "yes" ? true : selfTaken === "no" ? false : null,
        display_name: displayName,
        urls: validUrls,
      });
      // Check every link for the photo straight away, and optionally keep
      // watching (section 22.4). A link that can't be checked is noted, not fatal.
      const ids: string[] = [];
      const notes: string[] = [];
      // Each check is tied to its case link: when it finishes, the assistant
      // drafts that link's notice from what was found (section 23.4).
      for (const link of prints && checkNow ? created.links : []) {
        try {
          ids.push((await createDiscoveryJob(link.url, link.id)).id);
        } catch (e) {
          notes.push(`${link.url}: ${e instanceof ApiError ? e.message : "couldn't be checked"}`);
        }
      }
      for (const url of watch ? validUrls : []) {
        try {
          await addWatch({ url });
        } catch {}
      }
      setJobIds(ids);
      setScanNotes(notes);
      setNivraId(code);
      go("done");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong saving your case.");
    } finally {
      setBusy(false);
    }
  }

  async function copyId() {
    try {
      await navigator.clipboard.writeText(nivraId);
      setCopied(true);
    } catch {}
  }

  return (
    <div className="container narrow wizard">
      <div className="progress" aria-hidden="true">
        {ORDER.map((s, i) => (
          <span key={s} data-done={i <= stepIndex} />
        ))}
      </div>
      <p className="label">
        Step {stepIndex + 1} of {ORDER.length}
      </p>

      {step === "safety" && (
        <section>
          <h1>First, are you safe?</h1>
          <p className="wizard__intro">
            If you are in danger right now, call <a href="tel:112">112</a>. Otherwise, one
            question before we start.
          </p>
          <fieldset className="choices">
            <legend className="label" style={{ marginBottom: "var(--space-sm)" }}>
              Was the person in the image under 18 when it was taken?
            </legend>
            <label className="choice">
              <input
                type="radio"
                name="u18"
                checked={under18 === "no"}
                onChange={() => setUnder18("no")}
              />
              <span>
                <strong>No, they were 18 or older</strong>
              </span>
            </label>
            <label className="choice">
              <input
                type="radio"
                name="u18"
                checked={under18 === "yes"}
                onChange={() => setUnder18("yes")}
              />
              <span>
                <strong>Yes, or I&apos;m not sure</strong>
              </span>
            </label>
          </fieldset>
          {error && <p className="error">{error}</p>}
          <div className="wizard__nav">
            <Link href="/" className="btn btn--ghost">
              Cancel
            </Link>
            <button className="btn btn--primary" onClick={nextFromSafety}>
              Continue
            </button>
          </div>
        </section>
      )}

      {step === "minor" && (
        <section className="stack">
          <h1>These services can act faster than we can</h1>
          <p>
            Images of anyone under 18 are handled by specialist services with legal powers.
            Nivra does not store or process them. Here is what to do now:
          </p>
          <ol className="ladder">
            <li>
              <span>
                Use <a href={TAKE_IT_DOWN_URL} target="_blank" rel="noreferrer">Take It Down</a>{" "}
                to block the image on partner platforms. It works without sending the image.
              </span>
            </li>
            <li>
              <span>
                Report it at <a href="https://cybercrime.gov.in/" target="_blank" rel="noreferrer">cybercrime.gov.in</a>{" "}
                under &ldquo;Report Women/Child Related Crime&rdquo;.
              </span>
            </li>
            <li>
              <span>
                Call the cyber crime helpline on <a href="tel:1930">1930</a>.
              </span>
            </li>
          </ol>
          <p>Please don&apos;t share or forward the image, even to report it.</p>
          <div className="wizard__nav">
            <button className="btn btn--ghost" onClick={() => go("safety")}>
              Back
            </button>
            <Link href="/help" className="btn btn--primary">
              More help
            </Link>
          </div>
        </section>
      )}

      {step === "what" && (
        <section>
          <h1>What happened?</h1>
          <p className="wizard__intro">This decides which law and wording we use.</p>
          <fieldset className="choices">
            <legend className="sr-only">What happened</legend>
            {(Object.keys(CATEGORY_LABEL) as Category[]).map((c) => (
              <label key={c} className="choice">
                <input
                  type="radio"
                  name="cat"
                  checked={category === c}
                  onChange={() => setCategory(c)}
                />
                <span>
                  <strong>{CATEGORY_LABEL[c]}</strong>
                  <span className="small muted">{CATEGORY_HINT[c]}</span>
                </span>
              </label>
            ))}
          </fieldset>

          {category && category !== "morphed" && (
            <fieldset className="choices">
              <legend className="label" style={{ marginBottom: "var(--space-sm)" }}>
                Did you take the photo yourself? If so, you also own its copyright.
              </legend>
              {(
                [
                  ["yes", "Yes, I took it"],
                  ["no", "No, someone else did"],
                  ["unsure", "Not sure"],
                ] as const
              ).map(([v, l]) => (
                <label key={v} className="choice">
                  <input
                    type="radio"
                    name="self"
                    checked={selfTaken === v}
                    onChange={() => setSelfTaken(v)}
                  />
                  <span>
                    <strong>{l}</strong>
                  </span>
                </label>
              ))}
            </fieldset>
          )}
          {error && <p className="error">{error}</p>}
          <div className="wizard__nav">
            <button className="btn btn--ghost" onClick={() => go("safety")}>
              Back
            </button>
            <button className="btn btn--primary" onClick={nextFromWhat}>
              Continue
            </button>
          </div>
        </section>
      )}

      {step === "photo" && (
        <section>
          <h1>Add the photo</h1>
          <p className="wizard__intro">
            Nivra turns it into a 64-bit fingerprint on this device, then checks your links for it.
            The photo itself is never uploaded.
          </p>
          <label
            className="dropzone"
            data-over={over}
            onDragOver={(e) => {
              e.preventDefault();
              setOver(true);
            }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setOver(false);
              void choosePhoto(e.dataTransfer.files[0]);
            }}
          >
            <input
              type="file"
              accept="image/*"
              className="sr-only"
              onChange={(e) => void choosePhoto(e.target.files?.[0])}
            />
            <strong style={{ color: "var(--text)" }}>{photoUrl ? "Choose a different photo" : "Choose or drop the photo"}</strong>
            <span className="small muted">JPG, PNG or WebP. Stays on this device.</span>
          </label>
          {demo && (
            <p className="small muted" style={{ marginTop: "var(--space-sm)" }}>
              Demo mode:{" "}
              <button className="btn btn--small btn--ghost" onClick={() => void loadDemoPhoto()}>
                Use the demo photo
              </button>
            </p>
          )}

          {photoUrl && (
            <div className="preview-wrap" style={{ marginTop: "var(--space-lg)" }}>
              {/* eslint-disable-next-line @next/next/no-img-element -- local object URL */}
              <img src={photoUrl} alt="The photo you chose" className="preview" data-reveal={reveal} />
              <div className="stack" style={{ flex: 1, minWidth: "12rem" }}>
                <button className="btn btn--small btn--ghost" onClick={() => setReveal((r) => !r)}>
                  {reveal ? "Blur preview" : "Show preview"}
                </button>
                <div>
                  <p className="label" style={{ marginBottom: 6 }}>
                    {fpBusy ? "Fingerprinting..." : prints ? "Its fingerprint" : ""}
                  </p>
                  {prints && <BitGrid bits={prints.phash} />}
                  {prints && <p className="hash" style={{ marginTop: 6 }}>{prints.phash}</p>}
                </div>
              </div>
            </div>
          )}

          {prints && (
            <label className="check" style={{ marginTop: "var(--space-lg)" }}>
              <input type="checkbox" checked={authorised} onChange={(e) => setAuthorised(e.target.checked)} />
              <span className="small">
                I am the person in this photo, or I&apos;m acting with their permission. Only its
                fingerprint is stored, and I can delete it any time.
              </span>
            </label>
          )}
          {error && <p className="error" style={{ marginTop: "var(--space-md)" }}>{error}</p>}
          <div className="wizard__nav">
            <button className="btn btn--ghost" onClick={() => go("what")}>
              Back
            </button>
            <div className="actions">
              <button className="btn btn--ghost" onClick={skipPhoto}>
                I don&apos;t have it
              </button>
              <button className="btn btn--primary" onClick={nextFromPhoto} disabled={!prints || fpBusy}>
                Continue
              </button>
            </div>
          </div>
        </section>
      )}

      {step === "links" && (
        <section>
          <h1>Where is it?</h1>
          <p className="wizard__intro">
            Paste each link on its own line. You can add more later. Nivra will check each one for
            your photo.
          </p>
          <div className="field">
            <label htmlFor="links">Links</label>
            <textarea
              id="links"
              className="textarea"
              placeholder={"instagram.com/p/abc123\nt.me/somechannel/42"}
              value={linkText}
              onChange={(e) => setLinkText(e.target.value)}
            />
            {demo && (
              <div className="well small stack">
                <span>
                  <strong style={{ color: "var(--text)" }}>Demo mode.</strong> Five bundled demo
                  sites the real scanner can read:
                </span>
                <ul className="timeline">
                  {demo.links.map((d) => (
                    <li key={d.url}>
                      <span className="mono">{d.url.replace("https://", "")}</span>{" "}
                      <span className="muted">{d.about}</span>
                    </li>
                  ))}
                </ul>
                <div>
                  <button
                    className="btn btn--small"
                    onClick={() => setLinkText(demo.links.map((d) => d.url).join("\n"))}
                  >
                    Fill the demo links
                  </button>
                </div>
              </div>
            )}
            {parsed.length > 0 && (
              <ul className="detected" aria-live="polite">
                {parsed.map((p, i) => {
                  const platform = p.url ? resolvePlatform(p.url) : null;
                  return (
                    <li key={`${p.raw}-${i}`}>
                      <span className="url">{p.raw}</span>
                      <span className={p.url ? "muted" : "error"}>
                        {!p.url ? "Not a link" : platform ? platform.name : "Other website"}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
            {invalid.length > 0 && (
              <p className="hint">Lines that aren&apos;t links will be skipped.</p>
            )}
          </div>

          <details className="well">
            <summary style={{ cursor: "pointer", fontWeight: 500 }}>
              Don&apos;t know where it is yet?
            </summary>
            <div className="stack" style={{ marginTop: "var(--space-md)" }}>
              <p className="small">
                A reverse image search finds copies of a picture online. Open one of these, choose
                the image from your own device, and paste any links you find here. Note: the
                search engine will see the image you search with.
              </p>
              <div className="actions">
                {REVERSE_SEARCH.map((r) => (
                  <a
                    key={r.name}
                    className="btn btn--small"
                    href={r.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {r.name}
                  </a>
                ))}
              </div>
            </div>
          </details>

          {prints && (
            <div className="stack" style={{ marginTop: "var(--space-lg)" }}>
              <label className="check">
                <input type="checkbox" checked={checkNow} onChange={(e) => setCheckNow(e.target.checked)} />
                <span className="small">
                  <strong>Check these pages for my photo now.</strong> Nivra opens each page, reads
                  every image and compares fingerprints. You&apos;ll watch it happen.
                </span>
              </label>
              <label className="check">
                <input type="checkbox" checked={watch} onChange={(e) => setWatch(e.target.checked)} />
                <span className="small">
                  <strong>Keep watching them.</strong> Re-check regularly and tell me if the photo
                  comes back or a page goes down.
                </span>
              </label>
            </div>
          )}

          {error && <p className="error" style={{ marginTop: "var(--space-md)" }}>{error}</p>}
          <div className="wizard__nav">
            <button className="btn btn--ghost" onClick={() => go("photo")}>
              Back
            </button>
            <button className="btn btn--primary" onClick={nextFromLinks}>
              Continue with {validUrls.length} {validUrls.length === 1 ? "link" : "links"}
            </button>
          </div>
        </section>
      )}

      {step === "evidence" && (
        <section>
          <h1>Save proof before it&apos;s removed</h1>
          <p className="wizard__intro">
            Once a site removes it, the proof is gone too. If you want to go to the police later,
            save these now. A trusted friend can do this for you.
          </p>
          <ol className="ladder">
            <li>
              <span>A screenshot that shows the image, the web address and the date.</span>
            </li>
            <li>
              <span>The username or profile of whoever posted it.</span>
            </li>
            <li>
              <span>Any messages or threats connected to it.</span>
            </li>
          </ol>
          <p className="small muted" style={{ marginTop: "var(--space-md)" }}>
            Keep screenshots on your own device. Don&apos;t upload them anywhere, including here.
          </p>
          <label className="check" style={{ marginTop: "var(--space-lg)" }}>
            <input
              type="checkbox"
              checked={evidenceDone}
              onChange={(e) => setEvidenceDone(e.target.checked)}
            />
            <span>I&apos;ve saved what I can, or I&apos;ll do it later.</span>
          </label>
          <div className="wizard__nav">
            <button className="btn btn--ghost" onClick={() => go("links")}>
              Back
            </button>
            <button className="btn btn--primary" onClick={() => go("save")}>
              {evidenceDone ? "Continue" : "Skip for now"}
            </button>
          </div>
        </section>
      )}

      {step === "save" && (
        <section>
          <h1>{account ? "Save this case" : "Lock your case"}</h1>
          <p className="wizard__intro">
            {account ? (
              <>
                It will be added to your account <span className="num">{account.account_code}</span>.
              </>
            ) : (
              <>
                No email needed. You&apos;ll get a Nivra ID, and this passphrase opens it. We
                can&apos;t recover a lost passphrase.
              </>
            )}
          </p>
          <div className="field">
            <label htmlFor="name">Name to sign your notices (optional)</label>
            <input
              id="name"
              className="input"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              autoComplete="off"
            />
            <span className="hint">
              Platforms act faster on signed notices. Leave blank to fill it in later.
            </span>
          </div>
          {!account && (
            <>
              <div className="field">
                <label htmlFor="p1">Passphrase</label>
                <input
                  id="p1"
                  type="password"
                  className="input"
                  value={pass1}
                  onChange={(e) => setPass1(e.target.value)}
                  autoComplete="new-password"
                />
                <span className="hint">
                  At least 8 characters. A short sentence is easy to remember.
                </span>
              </div>
              <div className="field">
                <label htmlFor="p2">Type it again</label>
                <input
                  id="p2"
                  type="password"
                  className="input"
                  value={pass2}
                  onChange={(e) => setPass2(e.target.value)}
                  autoComplete="new-password"
                />
              </div>
            </>
          )}
          {error && <p className="error">{error}</p>}
          <div className="wizard__nav">
            <button className="btn btn--ghost" onClick={() => go("evidence")}>
              Back
            </button>
            <button className="btn btn--primary" onClick={save} disabled={busy}>
              {busy ? "Saving" : account ? "Save case" : "Create my case"}
            </button>
          </div>
        </section>
      )}

      {step === "done" && (
        <section className="stack-lg">
          <h1>Your case is ready</h1>
          <div className="slip">
            <p className="label">
              {account
                ? "Saved to your account."
                : "Your Nivra ID. Write it down somewhere safe."}
            </p>
            <p className="slip__id num">{nivraId}</p>
            <button className="btn btn--small" onClick={copyId}>
              {copied ? "Copied" : "Copy Nivra ID"}
            </button>
          </div>
          {jobIds.length > 0 && (
            <div className="stack">
              <h2>Checking your links now</h2>
              <p className="small muted">
                Each image on each page is fingerprinted and compared with yours. Where your photo
                is found, the assistant drafts the notice from what it found.
              </p>
              <LiveScan jobIds={jobIds} onFinished={setFinishedJobs} />
            </div>
          )}
          {finishedJobs && <ScanOutcome jobs={finishedJobs} />}
          {scanNotes.length > 0 && (
            <div className="well well--clay small">
              Some links couldn&apos;t be checked automatically:
              <ul className="timeline" style={{ marginTop: 6 }}>
                {scanNotes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </div>
          )}
          <p>
            Next, review each drafted notice in your case. One click approves it and Nivra sends it
            to the right place.
          </p>
          <div className="actions">
            <button className="btn btn--primary" onClick={() => router.push("/case")}>
              {finishedJobs ? "Review the drafted notices" : "Go to my case"}
            </button>
            {jobIds.length > 0 && (
              <Link href="/protect" className="btn">
                Review matches
              </Link>
            )}
          </div>
        </section>
      )}
    </div>
  );
}

/** After the checks: what happens to each link next (section 23.4). */
function ScanOutcome({ jobs }: { jobs: DiscoveryJob[] }) {
  const found = jobs.filter((j) => j.status === "done" && j.matches_found > 0);
  const missing = jobs.filter((j) => j.status === "done" && j.matches_found === 0);
  const blocked = jobs.filter((j) => j.status === "failed");
  const host = (u: string) => {
    try {
      return new URL(u).hostname;
    } catch {
      return u;
    }
  };
  return (
    <div className="well well--moss stack">
      <h3>What happens next</h3>
      <ul className="ladder small">
        {found.length > 0 && (
          <li>
            <span>
              <strong style={{ color: "var(--text)" }}>
                Your photo was found on {found.length} {found.length === 1 ? "page" : "pages"}
              </strong>{" "}
              ({found.map((j) => host(j.input_url)).join(", ")}). The assistant is drafting a
              notice for each, using what the scan found as evidence.
            </span>
          </li>
        )}
        {blocked.length > 0 && (
          <li>
            <span>
              {blocked.length} {blocked.length === 1 ? "page" : "pages"} couldn&apos;t be checked (
              {blocked.map((j) => host(j.input_url)).join(", ")}). Notices are drafted anyway,
              without claiming anything was verified.
            </span>
          </li>
        )}
        {missing.length > 0 && (
          <li>
            <span>
              Your photo wasn&apos;t found on {missing.map((j) => host(j.input_url)).join(", ")}, so
              no notice was drafted there. You can still prepare one.
            </span>
          </li>
        )}
      </ul>
    </div>
  );
}
