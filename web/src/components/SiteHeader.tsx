import Link from "next/link";
import QuickExit from "./QuickExit";

const NAV = [
  { href: "/start", label: "Start a case" },
  { href: "/case", label: "My case" },
  { href: "/guides", label: "Platform guides" },
  { href: "/help", label: "Get help now" },
];

export default function SiteHeader() {
  return (
    <header className="site-header">
      <p className="proto-note">
        Prototype. Cases are saved only in this browser. Press Esc twice to leave quickly.
      </p>
      <div className="container site-header__row">
        <Link href="/" className="wordmark">
          Nivra
        </Link>
        <nav className="nav" aria-label="Main">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href}>
              {n.label}
            </Link>
          ))}
        </nav>
        <details className="menu">
          <summary>Menu</summary>
          <div className="menu__panel">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href}>
                {n.label}
              </Link>
            ))}
          </div>
        </details>
        <QuickExit />
      </div>
    </header>
  );
}
