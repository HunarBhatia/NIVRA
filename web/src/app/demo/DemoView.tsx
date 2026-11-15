"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import BitGrid from "@/components/motion/BitGrid";
import ScanView, { type ScanCardData, type ScanStage } from "@/components/scan/ScanView";
import { fingerprintFile, type Fingerprints } from "@/lib/fingerprint";
import { hamming } from "@/lib/fingerprint/phash";

// In-browser demo (section 22.5). Runs the REAL fingerprinting code on
// sample images (or the visitor's own photo) entirely on this device, then
// plays the same scan view a real discovery job shows. Nothing is uploaded.

// Same thresholds as the backend (backend/app/core/config.py).
const HIGH = 6;
const POSSIBLE = 12;

type Candidate = { key: string; name: string; blob: Blob; url: string };

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function loadImage(blob: Blob): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = URL.createObjectURL(blob);
  });
}

function toBlob(canvas: HTMLCanvasElement, quality = 0.9): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("canvas"))), "image/jpeg", quality),
  );
}

/** The edits people make when they re-share a photo: crop, filter, shrink
 *  and recompress, add a caption. Generated here on a canvas. */
async function makeVariants(source: Blob): Promise<{ name: string; blob: Blob }[]> {
  const img = await loadImage(source);
  const w = img.naturalWidth, h = img.naturalHeight;
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d")!;

  canvas.width = Math.round(w * 0.84);
  canvas.height = Math.round(h * 0.84);
  ctx.drawImage(img, w * 0.08, h * 0.08, canvas.width, canvas.height, 0, 0, canvas.width, canvas.height);
  const cropped = await toBlob(canvas);

  canvas.width = w;
  canvas.height = h;
  ctx.filter = "brightness(1.18) contrast(1.15) saturate(1.5)";
  ctx.drawImage(img, 0, 0);
  ctx.filter = "none";
  const filtered = await toBlob(canvas);

  canvas.width = Math.max(64, Math.round(w * 0.28));
  canvas.height = Math.max(48, Math.round(h * 0.28));
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  const shrunk = await toBlob(canvas, 0.4);

  canvas.width = w;
  canvas.height = h;
  ctx.drawImage(img, 0, 0);
  ctx.fillStyle = "rgba(0,0,0,0.75)";
  ctx.fillRect(0, h * 0.84, w, h * 0.16);
  ctx.fillStyle = "#ffffff";
  ctx.font = `700 ${Math.round(h * 0.07)}px sans-serif`;
  ctx.textAlign = "center";
  ctx.fillText("reposted", w / 2, h * 0.945);
  const captioned = await toBlob(canvas);

  URL.revokeObjectURL(img.src);
  return [
    { name: "cropped.jpg", blob: cropped },
    { name: "filtered.jpg", blob: filtered },
    { name: "tiny-recompressed.jpg", blob: shrunk },
    { name: "with-caption.jpg", blob: captioned },
  ];
}

async function fetchBlob(path: string) {
  const r = await fetch(path);
  return r.blob();
}

function shuffle<T>(a: T[]): T[] {
  const b = [...a];
  for (let i = b.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [b[i], b[j]] = [b[j], b[i]];
  }
  return b;
}

export default function DemoView() {
  const [photo, setPhoto] = useState<{ blob: Blob; url: string; own: boolean } | null>(null);
  const [prints, setPrints] = useState<Fingerprints | null>(null);
  const [stage, setStage] = useState<ScanStage | null>(null);
  const [cards, setCards] = useState<ScanCardData[]>([]);
  const [error, setError] = useState("");
  const running = useRef(false);
  const urls = useRef<string[]>([]);

  const track = (u: string) => (urls.current.push(u), u);

  async function choosePhoto(blob: Blob, own: boolean) {
    setError("");
    setStage(null);
    setCards([]);
    setPrints(null);
    setPhoto({ blob, url: track(URL.createObjectURL(blob)), own });
    try {
      setPrints(await fingerprintFile(blob, { embedding: false }));
    } catch {
      setError("That image couldn't be read. Try a JPG or PNG.");
    }
  }

  useEffect(() => {
    fetchBlob("/demo/protected.jpg").then((b) => choosePhoto(b, false)).catch(() => setError("Couldn't load the sample."));
    const list = urls.current;
    return () => list.forEach((u) => URL.revokeObjectURL(u));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load the sample once
  }, []);

  async function run() {
    if (!photo || !prints || running.current) return;
    running.current = true;
    setError("");
    setCards([]);
    setStage("fetching");
    try {
      const variants = await makeVariants(photo.blob);
      const others = await Promise.all(["city", "forest", "ocean"].map(async (n) => ({ name: `${n}.jpg`, blob: await fetchBlob(`/demo/${n}.jpg`) })));
      const candidates: Candidate[] = shuffle([
        { name: "original-repost.jpg", blob: photo.blob },
        ...variants,
        ...others,
      ]).map((c, i) => ({ ...c, key: `c${i}`, url: track(URL.createObjectURL(c.blob)) }));
      await sleep(900);
      setStage("scanning");
      for (const c of candidates) {
        setCards((prev) => [...prev, { key: c.key, name: c.name, result: "checking", thumb: c.url }]);
        await sleep(650);
        const fp = await fingerprintFile(c.blob, { embedding: false });
        const distance = hamming(prints.phash, fp.phash);
        const exact = fp.sha256 === prints.sha256;
        const result = exact ? "exact" : distance <= HIGH ? "high" : distance <= POSSIBLE ? "possible" : "none";
        const diff = (BigInt(`0x${prints.phash}`) ^ BigInt(`0x${fp.phash}`)).toString(16).padStart(16, "0");
        setCards((prev) =>
          prev.map((p) =>
            p.key === c.key
              ? { ...p, result, phash: fp.phash, diff, distance, exact, label: photo.own ? "your photo" : "sample photo" }
              : p,
          ),
        );
        await sleep(250);
      }
      setStage("done");
    } catch {
      setStage("failed");
      setError("The demo hit a problem. Try again.");
    } finally {
      running.current = false;
    }
  }

  const found = cards.filter((c) => c.result === "exact" || c.result === "high" || c.result === "possible").length;

  return (
    <div className="container section stack-lg" style={{ paddingTop: "var(--space-xl)" }}>
      <div className="section-head" style={{ marginBottom: 0 }}>
        <h1>Watch Nivra find a copy.</h1>
        <p>
          This runs the real matching code in your browser. Copies that were cropped, filtered,
          shrunk or captioned still match. Different photos don&apos;t.
        </p>
      </div>

      <div className="dash-head" style={{ paddingBlock: 0 }}>
        <div className="well stack">
          <p className="label">{photo?.own ? "Your photo (stays on this device)" : "The protected photo (a sample)"}</p>
          <div className="preview-wrap" style={{ marginTop: 0, alignItems: "flex-start" }}>
            {photo && (
              /* eslint-disable-next-line @next/next/no-img-element -- local object URL */
              <img src={photo.url} alt="" className="preview" data-reveal={!photo.own} style={{ width: "11rem", height: "8.25rem" }} />
            )}
            <div className="stack" style={{ minWidth: "10rem" }}>
              <BitGrid bits={prints?.phash} />
              <p className="hash">{prints ? prints.phash : "fingerprinting..."}</p>
            </div>
          </div>
          <div className="actions">
            <button className="btn btn--primary" onClick={run} disabled={!prints || (stage !== null && stage !== "done" && stage !== "failed")}>
              {stage === "done" ? "Run it again" : "Run the scan"}
            </button>
            <label className="btn btn--ghost">
              Try my own photo
              <input
                type="file"
                accept="image/*"
                className="sr-only"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void choosePhoto(f, true);
                }}
              />
            </label>
          </div>
          {error && <p className="error">{error}</p>}
        </div>

        <div className="well well--moss stack">
          <h3>How the match works</h3>
          <ol className="ladder small">
            <li><span>The photo is shrunk to 32x32 greyscale and broken into frequencies (a DCT).</span></li>
            <li><span>The 64 lowest frequencies become 64 bits: above or below the median.</span></li>
            <li><span>Two photos are compared by counting the bits that differ. 0 to {HIGH} is a strong match, up to {POSSIBLE} is possible.</span></li>
          </ol>
        </div>
      </div>

      {stage && (
        <ScanView stage={stage} title="https://example-forum.test/thread/48213 (demo page)" cards={cards} />
      )}

      {stage === "done" && (
        <div className="well actions" style={{ justifyContent: "space-between" }}>
          <p>
            <strong style={{ color: "var(--text)" }}>{found} copies found</strong> out of {cards.length} images. In a
            real case you confirm each one, approve the notice once, and Nivra sends it.
          </p>
          <Link href="/start" className="btn btn--primary">
            Start a real case
          </Link>
        </div>
      )}
    </div>
  );
}
