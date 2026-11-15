"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export const NAV = [
  { href: "/start", label: "Start a case" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/protect", label: "Protect & scan" },
  { href: "/demo", label: "See it work" },
  { href: "/guides", label: "Guides" },
  { href: "/help", label: "Get help" },
];

export default function NavLinks() {
  const path = usePathname();
  return NAV.map((n) => (
    <Link key={n.href} href={n.href} aria-current={path.startsWith(n.href) ? "page" : undefined}>
      {n.label}
    </Link>
  ));
}
