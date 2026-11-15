import Link from "next/link";
import BitGrid from "@/components/motion/BitGrid";
import CountUp from "@/components/motion/CountUp";
import FingerprintHero from "@/components/motion/FingerprintHero";
import Reveal from "@/components/motion/Reveal";

// Landing page (section 22.3). Someone arriving may be in shock, so the
// first screen stays short: one headline, one sentence, one action. Below
// it, the page SHOWS the machinery: fingerprint, scan, compare, send.

// Illustrative hashes for the pipeline cards (not real user data).
const SAMPLE = "c3a5e91f0d6b7248";
const SAMPLE_COPY = "c3a5e91f0d6b7a48";
const SAMPLE_DIFF = "0000000000000c00";

const PIPELINE = [
  {
    n: "01",
    title: "Fingerprint, on your device",
    text: "Your photo is turned into 64 bits inside your browser. The photo itself never leaves.",
    visual: <BitGrid bits={SAMPLE} label="An example 64-bit fingerprint" />,
  },
  {
    n: "02",
    title: "Scan the pages",
    text: "Nivra visits every link you found and reads each image on the page.",
    visual: (
      <div className="scan-card__thumb" aria-hidden="true">
        <div className="scan-card__beam scan-loop" />
      </div>
    ),
  },
  {
    n: "03",
    title: "Compare bit by bit",
    text: "Crops, filters and re-uploads still match: only a few bits change.",
    visual: <BitGrid bits={SAMPLE_COPY} diff={SAMPLE_DIFF} label="A near copy: two bits differ" />,
  },
  {
    n: "04",
    title: "Send and track",
    text: "Approve once. Nivra emails the notice to the platform or host and watches the link.",
    visual: (
      <div className="actions" aria-hidden="true">
        <span className="badge" data-tone="good">Sent by Nivra</span>
        <span className="badge">Watching</span>
      </div>
    ),
  },
];

const ICONS = {
  lock: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <rect x="4" y="10" width="16" height="11" rx="2.5" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
    </svg>
  ),
  mail: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <rect x="3" y="5" width="18" height="14" rx="2.5" />
      <path d="m4 7 8 6 8-6" />
    </svg>
  ),
  eye: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  ),
  scale: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <path d="M12 3v18M5 7h14M5 7l-3 7h6L5 7Zm14 0-3 7h6l-3-7Z" />
    </svg>
  ),
  vault: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <circle cx="12" cy="12" r="3.5" />
      <path d="M12 8.5V7M12 17v-1.5" />
    </svg>
  ),
};

const FEATURES = [
  {
    icon: ICONS.eye,
    title: "It shows you what it found",
    text: "Every image on every page, scored live. You confirm each match before anything happens.",
    tone: "",
  },
  {
    icon: ICONS.mail,
    title: "One approval, then it sends",
    text: "Notices go straight to the platform's or host's abuse desk, with replies coming back to you.",
    tone: "tile--violet",
  },
  {
    icon: ICONS.scale,
    title: "Written to Indian law",
    text: "IT Rules 2021 and the 24-hour removal rule for intimate images, cited for you.",
    tone: "tile--violet",
  },
  {
    icon: ICONS.vault,
    title: "Evidence, sealed",
    text: "Screenshots are encrypted in your browser with your passphrase before they are stored.",
    tone: "",
  },
  {
    icon: ICONS.lock,
    title: "No name, no phone",
    text: "A Nivra ID and a passphrase are all you need to come back.",
    tone: "tile--violet",
  },
];

export default function Home() {
  return (
    <>
      <section className="hero">
        <FingerprintHero />
        <div className="container">
          <div className="hero__content">
            <h1>
              Find it. Prove it. <span className="gradient-text">Take it down.</span>
            </h1>
            <p className="hero__lede">
              Nivra scans the pages, matches your photo by fingerprint and sends the takedown for
              you.
            </p>
            <div className="actions">
              <Link href="/start" className="btn btn--primary">
                Start a case
              </Link>
              <Link href="/demo" className="btn">
                Watch a scan
              </Link>
            </div>
          </div>
        </div>
      </section>

      <Reveal as="section" className="section">
        <div className="container">
          <div className="section-head" data-reveal>
            <h2>What happens to your photo.</h2>
            <p>Four steps, and the first one never leaves your phone.</p>
          </div>
          <ol className="pipeline" style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {PIPELINE.map((p) => (
              <li key={p.n} className="pipe-card" data-reveal>
                <span className="pipe-card__n">{p.n}</span>
                <h3>{p.title}</h3>
                <p className="small">{p.text}</p>
                <div style={{ marginTop: "auto" }}>{p.visual}</div>
              </li>
            ))}
          </ol>
        </div>
      </Reveal>

      <Reveal as="section" className="section">
        <div className="container">
          <div className="section-head" data-reveal>
            <h2>Built for the worst week of someone&apos;s life.</h2>
          </div>
          <div className="bento">
            {FEATURES.map((f) => (
              <article key={f.title} className={`tile ${f.tone}`} data-reveal>
                <span className="tile__icon">{f.icon}</span>
                <h3>{f.title}</h3>
                <p className="small">{f.text}</p>
              </article>
            ))}
          </div>
        </div>
      </Reveal>

      <Reveal as="section" className="section">
        <div className="container">
          <div className="privacy-band" data-reveal>
            <p className="statement">We never see your photo. Not once.</p>
            <div className="facts">
              <div>
                <strong>
                  <CountUp to={0} />
                </strong>
                <span className="small">photos uploaded to Nivra, ever</span>
              </div>
              <div>
                <strong>
                  <CountUp to={64} /> bits
                </strong>
                <span className="small">is all that leaves your device</span>
              </div>
              <div>
                <strong>
                  <CountUp to={24} /> hours
                </strong>
                <span className="small">for platforms to remove intimate images under Indian law</span>
              </div>
            </div>
          </div>
        </div>
      </Reveal>

      <Reveal as="section" className="section">
        <div className="container actions" style={{ justifyContent: "space-between" }} data-reveal>
          <div>
            <h2>See a scan before you trust us.</h2>
            <p className="small" style={{ marginTop: "var(--space-xs)" }}>
              The demo runs the real matching in your browser on sample images.
            </p>
          </div>
          <div className="actions">
            <Link href="/demo" className="btn btn--primary">
              Run the demo
            </Link>
            <Link href="/help" className="btn btn--ghost">
              Get help now
            </Link>
          </div>
        </div>
        <p className="container small muted" style={{ marginTop: "var(--space-xl)" }}>
          If the person in the image was under 18, <Link href="/help#under-18">use these services
          instead</Link>. They have legal powers we don&apos;t.
        </p>
      </Reveal>
    </>
  );
}
