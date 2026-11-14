"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { WatchedPage } from "@/lib/types";

// "Watch this page" for one case link (section 20.3). Watching is the user's
// standing approval for Nivra to re-check the page on a schedule.

let cache: Promise<WatchedPage[]> | null = null;
const watches = () => (cache ??= api.listWatches());

export default function WatchToggle({ linkId, url }: { linkId: string; url: string }) {
  const [watch, setWatch] = useState<WatchedPage | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    watches()
      .then((all) => setWatch(all.find((w) => w.link_id === linkId || w.url === url) ?? null))
      .catch(() => setWatch(null));
  }, [linkId, url]);

  async function toggle() {
    setBusy(true);
    setError("");
    try {
      if (watch) {
        await api.removeWatch(watch.id);
        setWatch(null);
      } else {
        setWatch(await api.addWatch({ link_id: linkId, interval_hours: 24 }));
      }
      cache = null;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  if (watch === undefined) return null;
  return (
    <div className="stack">
      <h3>Monitoring</h3>
      <p className="small">
        {watch
          ? `Nivra re-checks this page ${watch.enabled ? "every day" : "(paused)"} and tells you if it stops loading or the image comes back.`
          : "Have Nivra re-check this page every day and tell you if it stops loading or the image comes back."}
      </p>
      <div className="actions">
        <button className="btn btn--small" disabled={busy} onClick={toggle}>
          {watch ? "Stop watching" : "Watch this page"}
        </button>
        {watch && <Link className="small" href="/settings">Change how often</Link>}
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
