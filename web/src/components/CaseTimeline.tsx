"use client";

import { useEffect, useState } from "react";
import * as api from "@/lib/api";
import type { TimelineItem } from "@/lib/types";

// Everything that happened in a case, newest first (section 18.7).

export default function CaseTimeline({ caseId, version }: { caseId: string; version: number }) {
  const [items, setItems] = useState<TimelineItem[] | null>(null);

  useEffect(() => {
    api.getTimeline(caseId).then(setItems).catch(() => setItems([]));
  }, [caseId, version]);

  if (!items) return null;
  return (
    <section className="section stack" aria-labelledby="tl-h" style={{ paddingTop: 0 }}>
      <h2 id="tl-h">Timeline</h2>
      {items.length === 0 ? (
        <p className="well">Nothing yet.</p>
      ) : (
        <ul className="timeline">
          {items.slice(0, 50).map((i, n) => (
            <li key={n}>
              <time className="num" dateTime={i.at}>
                {new Date(i.at).toLocaleString("en-IN", {
                  day: "numeric",
                  month: "short",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </time>
              {i.host ? <span className="muted">{i.host}: </span> : null}
              {i.text}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
