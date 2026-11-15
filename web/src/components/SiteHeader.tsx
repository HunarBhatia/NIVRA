import Link from "next/link";
import Logo from "./Logo";
import NavLinks from "./NavLinks";
import QuickExit from "./QuickExit";
import UpdatesLink from "./UpdatesLink";

export default function SiteHeader() {
  return (
    <header className="site-header">
      <p className="proto-note">
        Prototype: please use test details only. Press Esc twice to leave quickly.
      </p>
      <div className="container site-header__row">
        <Link href="/" className="wordmark" aria-label="Nivra home">
          <Logo />
          <span>Nivra</span>
        </Link>
        <nav className="nav" aria-label="Main">
          <NavLinks />
        </nav>
        <details className="menu">
          <summary>Menu</summary>
          <div className="menu__panel">
            <NavLinks />
          </div>
        </details>
        <UpdatesLink />
        <QuickExit />
      </div>
    </header>
  );
}
