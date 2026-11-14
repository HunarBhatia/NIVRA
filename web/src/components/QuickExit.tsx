"use client";

import { useEffect } from "react";

// Quick exit (feature 7.1). Logs the account out on the server, then replaces
// this tab with a harmless page so the back button doesn't return to Nivra.
// Shortcut: press Esc twice quickly.

const SAFE_URL = "https://www.google.com/search?q=weather+today";

export function quickExit() {
  try {
    // sendBeacon survives the page unloading, so the session is ended
    // server-side even though we leave immediately.
    navigator.sendBeacon?.("/api/auth/logout");
  } catch {}
  try {
    sessionStorage.clear();
  } catch {}
  window.location.replace(SAFE_URL);
}

export default function QuickExit() {
  useEffect(() => {
    let last = 0;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const now = Date.now();
      if (now - last < 800) quickExit();
      last = now;
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <button
      type="button"
      className="btn btn--small quick-exit"
      onClick={quickExit}
      title="Leave this site now (or press Esc twice)"
    >
      Quick exit
    </button>
  );
}
