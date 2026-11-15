"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";
import BitGrid from "@/components/motion/BitGrid";

/** The live scan view (section 22.5): shows Nivra reading every image on a
 *  page, fingerprinting it and comparing it with the protected photo, bit by
 *  bit. Used by real discovery jobs (from scan_log) and by the in-browser
 *  demo. Real scans never load the found images: only hashes are shown. */

export type ScanStage = "queued" | "fetching" | "scanning" | "done" | "failed";
export type ScanResult = "exact" | "high" | "possible" | "none" | "unreadable" | "checking";

export interface ScanCardData {
  key: string;
  name: string;
  result: ScanResult;
  /** Found image's 64-bit fingerprint (hex). */
  phash?: string | null;
  /** Bits that differ from the closest protected photo (hex). */
  diff?: string | null;
  distance?: number | null;
  exact?: boolean;
  label?: string;
  /** Only the demo shows thumbnails (its own sample images). */
  thumb?: string;
}

const STAGES: { id: ScanStage; label: string }[] = [
  { id: "queued", label: "Queued" },
  { id: "fetching", label: "Opening the page" },
  { id: "scanning", label: "Fingerprinting images" },
  { id: "done", label: "Done" },
];

const VERDICT: Record<ScanResult, string> = {
  exact: "Exact copy",
  high: "Strong match",
  possible: "Possible match",
  none: "Not your photo",
  unreadable: "Couldn't read",
  checking: "Checking...",
};

function xorHex(a: string, b: string) {
  try {
    return (BigInt(`0x${a}`) ^ BigInt(`0x${b}`)).toString(16).padStart(16, "0");
  } catch {
    return null;
  }
}

function stageState(current: ScanStage, s: ScanStage) {
  if (current === "failed") return s === "queued" ? "done" : "idle";
  const order = STAGES.map((x) => x.id);
  const ci = order.indexOf(current), si = order.indexOf(s);
  if (si < ci || (current === "done" && s === "done")) return "done";
  return si === ci ? "active" : "idle";
}

export function ScanCard({ d }: { d: ScanCardData }) {
  const ref = useRef<HTMLDivElement>(null);
  const yours = d.phash && d.diff ? xorHex(d.phash, d.diff) : null;
  const similarity = d.distance != null ? Math.max(0, (64 - d.distance) / 64) : null;
  const hit = d.result === "exact" || d.result === "high" || d.result === "possible";

  useEffect(() => {
    if (!ref.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t = gsap.fromTo(ref.current, { opacity: 0, y: 18, scale: 0.97 },
      { opacity: 1, y: 0, scale: 1, duration: 0.55, ease: "power3.out" });
    return () => { t.kill(); };
  }, []);

  useEffect(() => {
    if (!hit || !ref.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t = gsap.fromTo(ref.current, { boxShadow: "0 0 0 0 rgba(255,138,112,0.7)" },
      { boxShadow: "0 0 0 14px rgba(255,138,112,0)", duration: 1.1, ease: "power2.out", repeat: 1 });
    return () => { t.kill(); };
  }, [hit]);

  return (
    <div ref={ref} className="scan-card" data-result={d.result}>
      <div className="scan-card__thumb">
        {/* eslint-disable-next-line @next/next/no-img-element -- local demo samples only */}
        {d.thumb && <img src={d.thumb} alt="" />}
        {d.result === "checking" && <div className="scan-card__beam scan-loop" />}
      </div>
      <div className="scan-card__row">
        <span className="small" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={d.name}>
          {d.name}
        </span>
        <span className="verdict" data-result={d.result}>{VERDICT[d.result]}</span>
      </div>
      {d.phash && (
        <div className="scan-card__row" style={{ alignItems: "flex-start" }}>
          <div style={{ display: "grid", gap: 4, flex: 1 }}>
            <span className="label">{yours ? "Your photo" : "Found"}</span>
            <BitGrid bits={yours ?? d.phash} label="Your photo's fingerprint" />
          </div>
          {yours && (
            <div style={{ display: "grid", gap: 4, flex: 1 }}>
              <span className="label">Found here</span>
              <BitGrid bits={d.phash} diff={d.diff} label={`Found image fingerprint, ${d.distance} bits differ`} />
            </div>
          )}
        </div>
      )}
      {similarity != null && (
        <>
          <div className="meter" aria-hidden="true">
            <span style={{ transform: `scaleX(${similarity})` }} />
          </div>
          <span className="hash">
            {d.exact ? "identical file" : `${d.distance} of 64 bits differ`}
            {d.label ? ` vs "${d.label}"` : ""}
          </span>
        </>
      )}
    </div>
  );
}

export default function ScanView({ stage, title, cards, error }: {
  stage: ScanStage;
  title: string;
  cards: ScanCardData[];
  error?: string | null;
}) {
  const hits = cards.filter((c) => c.result === "exact" || c.result === "high" || c.result === "possible").length;
  const checked = cards.filter((c) => c.result !== "checking").length;
  return (
    <section className="scan well" aria-label={`Scan of ${title}`}>
      <div className="actions" style={{ justifyContent: "space-between" }}>
        <div style={{ minWidth: 0 }}>
          <p className="label">Scanning</p>
          <p className="mono small" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--text)" }}>
            {title}
          </p>
        </div>
        <span className="badge" data-tone={hits > 0 ? "warn" : stage === "done" ? "good" : undefined} aria-live="polite">
          {checked} checked, {hits} {hits === 1 ? "match" : "matches"}
        </span>
      </div>
      <div className="scan__stage">
        {STAGES.map((s) => (
          <span key={s.id} className="scan__step" data-state={stageState(stage, s.id)}>
            {s.label}
          </span>
        ))}
        {stage === "failed" && <span className="scan__step" data-state="failed">Stopped</span>}
      </div>
      {error && <p className="error">{error}</p>}
      {cards.length > 0 ? (
        <div className="scan__grid">
          {cards.map((c) => (
            <ScanCard key={c.key} d={c} />
          ))}
        </div>
      ) : (
        stage !== "done" && stage !== "failed" && (
          <div className="scan-card__thumb" style={{ height: "4rem" }}>
            <div className="scan-card__beam scan-loop" />
          </div>
        )
      )}
      {stage === "done" && cards.length === 0 && (
        <p className="small muted">No images could be read on this page.</p>
      )}
    </section>
  );
}
