import Link from "next/link";

// Landing page. Kept short on purpose: someone arriving here may be in shock.
// One headline, one promise, one action.

const STEPS = [
  {
    title: "Paste the links",
    text: "Add every place you've found it. You never upload the image itself.",
  },
  {
    title: "We find who to tell",
    text: "Nivra knows each platform's reporting route and the law that applies.",
  },
  {
    title: "Send the notice",
    text: "We write it for you, citing India's 24-hour removal rule.",
  },
  {
    title: "Track until it's gone",
    text: "See every link's status, and what to do if a site goes quiet.",
  },
];

const HELPS = [
  {
    title: "Intimate images",
    text: "Photos or videos shared without your consent, by anyone, anywhere.",
  },
  {
    title: "Morphed and deepfake images",
    text: "Fake images made with your face. They are covered by the same law.",
  },
  {
    title: "Fake profiles",
    text: "Accounts pretending to be you, using your photos.",
  },
];

export default function Home() {
  return (
    <>
      <section className="container hero">
        <div>
          <h1>Get it taken down, quietly.</h1>
          <p className="hero__lede">
            Nivra writes every takedown notice and tracks each link until it&apos;s gone.
          </p>
          <div className="actions">
            <Link href="/start" className="btn btn--primary">
              Start a case
            </Link>
            <Link href="/case" className="btn">
              Open my case
            </Link>
          </div>
        </div>

        <aside className="slip" aria-label="What you get">
          <p className="label">Your case, without your name</p>
          <p className="slip__id num">NV-7K3Q-92XD</p>
          <div className="slip__rows">
            <div className="slip__row">
              <span>Accounts or email</span>
              <span>Not needed</span>
            </div>
            <div className="slip__row">
              <span>Your images</span>
              <span>Never leave your phone</span>
            </div>
            <div className="slip__row">
              <span>To return</span>
              <span>Nivra ID and a passphrase</span>
            </div>
          </div>
        </aside>
      </section>

      <section className="section band--ink">
        <div className="container">
          <p className="statement">We never see your images. Not once.</p>
          <p className="small" style={{ marginTop: "var(--space-md)" }}>
            Nivra only works with links. Nothing you would not want stored is ever stored.
          </p>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <h2>How it works</h2>
          <ol className="steps">
            {STEPS.map((s, i) => (
              <li key={s.title}>
                <span className="steps__n" aria-hidden="true">
                  {i + 1}
                </span>
                <h3>{s.title}</h3>
                <p className="small">{s.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <h2>What Nivra can help with</h2>
          <ul className="rows">
            {HELPS.map((h) => (
              <li key={h.title}>
                <h3>{h.title}</h3>
                <p className="small">{h.text}</p>
                <span />
              </li>
            ))}
          </ul>
          <p className="small muted" style={{ marginTop: "var(--space-lg)" }}>
            If the person in the image was under 18, <Link href="/help#under-18">use these
            services instead</Link>. They have legal powers we don&apos;t.
          </p>
        </div>
      </section>

      <section className="section band--moss">
        <div className="container actions" style={{ justifyContent: "space-between" }}>
          <div>
            <h2>You don&apos;t have to do this alone.</h2>
            <p className="small" style={{ marginTop: "var(--space-xs)" }}>
              Helplines, counselling and legal aid, all in one place.
            </p>
          </div>
          <Link href="/help" className="btn">
            Get help now
          </Link>
        </div>
      </section>
    </>
  );
}
