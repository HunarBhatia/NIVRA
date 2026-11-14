import Link from "next/link";

export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="container site-footer__row">
        <p>
          In danger right now? Call <a href="tel:112">112</a>. Cyber crime helpline{" "}
          <a href="tel:1930">1930</a>.
        </p>
        <p>
          Nivra gives templates and guidance, not legal advice. <Link href="/help">Find support</Link>
        </p>
      </div>
    </footer>
  );
}
