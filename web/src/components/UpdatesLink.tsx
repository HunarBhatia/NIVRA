"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import * as api from "@/lib/api";

// "Updates" in the header, with the number of unread notifications. Shown only
// when someone is logged in; checks again every minute.

export default function UpdatesLink() {
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    const check = () =>
      api
        .unreadCount()
        .then((r) => alive && setCount(r.unread))
        .catch(() => alive && setCount(null)); // logged out (401) or offline: hide
    check();
    const t = setInterval(check, 60_000);
    window.addEventListener("focus", check);
    return () => {
      alive = false;
      clearInterval(t);
      window.removeEventListener("focus", check);
    };
  }, []);

  if (count === null) return null;
  return (
    <Link href="/notifications" className="updates-link" aria-label={`Updates, ${count} unread`}>
      <span className="updates-text">Updates</span>{count > 0 && <span className="updates-count num">{count}</span>}
    </Link>
  );
}
