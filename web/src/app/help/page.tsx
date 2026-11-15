import type { Metadata } from "next";
import { CYBERCRIME_URL, STOPNCII_URL, TAKE_IT_DOWN_URL } from "@/lib/platforms";

export const metadata: Metadata = { title: "Get help now" };

// PROTOTYPE DATA: verify every number before public launch.
const URGENT = [
  { name: "Emergency", detail: "Police, ambulance, fire", phone: "112" },
  { name: "National Cyber Crime Helpline", detail: "Report online crimes, 24 hours", phone: "1930" },
  { name: "Women Helpline", detail: "Support for women in distress", phone: "181" },
  { name: "Tele-MANAS", detail: "Free mental health support, 24 hours", phone: "14416" },
];

export default function HelpPage() {
  return (
    <div className="container narrow section stack-lg">
      <div>
        <h1>Get help now</h1>
        <p style={{ marginTop: "var(--space-sm)" }}>
          What happened is not your fault. You can talk to someone today, for free.
        </p>
      </div>

      <section aria-labelledby="urgent">
        <h2 id="urgent">Call someone</h2>
        <ul className="rows">
          {URGENT.map((u) => (
            <li key={u.phone}>
              <h3>{u.name}</h3>
              <p className="small">{u.detail}</p>
              <a className="btn btn--small num" href={`tel:${u.phone}`}>
                Call {u.phone}
              </a>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="report" className="stack">
        <h2 id="report">Report it to the police</h2>
        <p>
          You can file a complaint online at the National Cyber Crime Reporting Portal. Choose
          &ldquo;Report Women/Child Related Crime&rdquo;. You can report anonymously, but a named
          complaint lets the police follow up.
        </p>
        <a className="btn" href={CYBERCRIME_URL} target="_blank" rel="noreferrer">
          Open cybercrime.gov.in
        </a>
      </section>

      <section aria-labelledby="spread" className="stack">
        <h2 id="spread">Stop it spreading on big platforms</h2>
        <p>
          StopNCII makes a digital fingerprint of your image on your own device. Partner
          platforms, including Facebook, Instagram, TikTok and Reddit, then block matching
          uploads. The image itself is never sent.
        </p>
        <a className="btn" href={STOPNCII_URL} target="_blank" rel="noreferrer">
          Open StopNCII.org
        </a>
      </section>

      <section id="under-18" aria-labelledby="minors" className="well well--clay stack">
        <h2 id="minors">If the person was under 18</h2>
        <p>
          Nivra does not handle these images. Use Take It Down, which blocks them on partner
          platforms, and report to the cyber crime portal or call 1930. These services can act
          with legal powers that we don&apos;t have.
        </p>
        <div className="actions">
          <a className="btn btn--primary" href={TAKE_IT_DOWN_URL} target="_blank" rel="noreferrer">
            Open Take It Down
          </a>
          <a className="btn" href="tel:1930">
            Call 1930
          </a>
        </div>
      </section>

      <section aria-labelledby="talk" className="stack">
        <h2 id="talk">Look after yourself</h2>
        <p>
          You don&apos;t have to look at the content again to deal with it. A trusted friend can
          open your case and do the reporting for you, using your Nivra ID and passphrase.
        </p>
      </section>
    </div>
  );
}
