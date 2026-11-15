"use client";

import type { LinkScan } from "@/lib/types";
import { similarityPct } from "./ScanView";

/** "What Nivra found" for one case link (section 23.3): the result of
 *  checking the page for the user's photo, which decides whether the
 *  assistant drafts a notice and becomes that notice's evidence. */

const STRENGTH: Record<string, string> = {
  exact: "an exact copy",
  high: "a strong match (an edited copy)",
  possible: "a possible match (a heavily edited copy)",
};

export default function ScanFindings({
  scan,
  drafting,
  hasNotice,
  onCheck,
  checking,
  error,
}: {
  scan: LinkScan | undefined;
  drafting: boolean;
  hasNotice: boolean;
  onCheck: () => void;
  checking: boolean;
  error: string;
}) {
  const running = scan && (scan.status === "queued" || scan.status === "running");
  const found = scan?.status === "done" && scan.matches_found > 0;
  const notFound = scan?.status === "done" && scan.matches_found === 0;

  return (
    <div className={`well stack ${found ? "well--clay" : ""}`}>
      <h3>What Nivra found</h3>
      {!scan && (
        <>
          <p className="small">This page hasn&apos;t been checked for your photo yet.</p>
          <div>
            <button className="btn btn--small" onClick={onCheck} disabled={checking}>
              {checking ? "Starting..." : "Check this page for my photo"}
            </button>
          </div>
        </>
      )}
      {running && (
        <>
          <p className="small" aria-live="polite">
            {scan.stage === "scanning"
              ? `Fingerprinting the images on the page (${scan.images_checked} so far)...`
              : "Opening the page..."}
          </p>
          <div className="scan-card__thumb" style={{ height: "0.5rem" }} aria-hidden="true">
            <div className="scan-card__beam scan-loop" />
          </div>
        </>
      )}
      {found && (
        <p className="small">
          <strong style={{ color: "var(--text)" }}>Your photo is on this page:</strong>{" "}
          {STRENGTH[scan.best ?? "possible"]}
          {scan.best !== "exact" && scan.distance != null
            ? `: ${similarityPct(scan.distance)}% similar (${scan.distance} of 64 fingerprint bits differ)`
            : ""}
          . {scan.images_checked} {scan.images_checked === 1 ? "image" : "images"} checked.
        </p>
      )}
      {scan?.scripted && (
        <p className="hint" role="note">
          Scripted demo result: this site blocks automated checks, so the page was served from a
          local copy. The comparison itself is real.
        </p>
      )}
      {notFound && (
        <p className="small">
          Checked {scan.images_checked} {scan.images_checked === 1 ? "image" : "images"}: your photo
          wasn&apos;t found here, so no notice was drafted. It may have been removed or changed a
          lot. If you know it&apos;s there, prepare a notice anyway below.
        </p>
      )}
      {scan?.status === "failed" && (
        <p className="small">
          Couldn&apos;t check this page automatically: {scan.error_message}
          {hasNotice || drafting ? " The notice was drafted anyway; it doesn't claim anything was verified." : ""}
        </p>
      )}
      {drafting && (
        <p className="small" aria-live="polite">
          <strong style={{ color: "var(--teal)" }}>The assistant is drafting the notice</strong> from
          these findings...
        </p>
      )}
      {scan && !running && (
        <div>
          <button className="btn btn--small btn--ghost" onClick={onCheck} disabled={checking}>
            {checking ? "Starting..." : "Check again"}
          </button>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
