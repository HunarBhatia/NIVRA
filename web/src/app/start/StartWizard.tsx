"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { createCase } from "@/lib/caseStore";
import { CATEGORY_LABEL } from "@/lib/notices";
import { TAKE_IT_DOWN_URL, normaliseUrl, resolvePlatform, splitLinks } from "@/lib/platforms";
import type { Category } from "@/lib/types";

// The "Start a case" wizard (blueprint 10.2). One decision per screen.

type Step = "safety" | "minor" | "what" | "links" | "evidence" | "save" | "done";
const ORDER: Step[] = ["safety", "what", "links", "evidence", "save", "done"];

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
  const [caseId, setCaseId] = useState("");
  const [copied, setCopied] = useState(false);

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
    go("links");
  }

  function nextFromLinks() {
    if (validUrls.length === 0) return setError("Add at least one link, like instagram.com/p/...");
    go("evidence");
  }

  async function save() {
    if (pass1.length < 8) return setError("Use at least 8 characters for your passphrase.");
    if (pass1 !== pass2) return setError("The two passphrases don't match.");
    setBusy(true);
    try {
      const c = await createCase({
        category: category as Category,
        selfTaken: selfTaken === "yes" ? true : selfTaken === "no" ? false : null,
        displayName,
        passphrase: pass1,
        urls: validUrls,
      });
      setCaseId(c.id);
      go("done");
    } catch {
      setError("Something went wrong saving your case. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function copyId() {
    try {
      await navigator.clipboard.writeText(caseId);
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

      {step === "links" && (
        <section>
          <h1>Where is it?</h1>
          <p className="wizard__intro">
            Paste each link on its own line. You can add more later. We only need the link, never
            the image.
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

          {error && <p className="error" style={{ marginTop: "var(--space-md)" }}>{error}</p>}
          <div className="wizard__nav">
            <button className="btn btn--ghost" onClick={() => go("what")}>
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
          <h1>Lock your case</h1>
          <p className="wizard__intro">
            No account or email. You&apos;ll get a Case ID, and this passphrase opens it. We
            can&apos;t recover a lost passphrase.
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
            <span className="hint">At least 8 characters. A short sentence is easy to remember.</span>
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
          {error && <p className="error">{error}</p>}
          <div className="wizard__nav">
            <button className="btn btn--ghost" onClick={() => go("evidence")}>
              Back
            </button>
            <button className="btn btn--primary" onClick={save} disabled={busy}>
              {busy ? "Saving" : "Create my case"}
            </button>
          </div>
        </section>
      )}

      {step === "done" && (
        <section className="stack-lg">
          <h1>Your case is ready</h1>
          <div className="slip">
            <p className="label">Your Case ID. Write it down somewhere safe.</p>
            <p className="slip__id num">{caseId}</p>
            <button className="btn btn--small" onClick={copyId}>
              {copied ? "Copied" : "Copy Case ID"}
            </button>
          </div>
          <p>
            Next, we&apos;ll show you a notice for each link and exactly where to send it.
          </p>
          <div className="actions">
            <button className="btn btn--primary" onClick={() => router.push("/case")}>
              Go to my case
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
