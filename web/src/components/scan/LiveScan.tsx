"use client";

import { useEffect, useState } from "react";
import * as api from "@/lib/api";
import type { DiscoveryJob } from "@/lib/types";
import ScanView, { type ScanCardData } from "./ScanView";

/** Follows real discovery jobs live: polls each job and animates its
 *  scan_log as the worker fingerprints the images on the page. */

function nameOf(url: string) {
  try {
    const u = new URL(url);
    const file = u.pathname.split("/").filter(Boolean).pop() ?? "";
    return `${u.hostname}/${file.slice(0, 40)}`;
  } catch {
    return url.slice(0, 60);
  }
}

/** Only the bundled demo sites (*.test, Nivra's own drawn images) get
 *  thumbnails; real scans never load found images (section 22.10). */
function demoThumb(url: string) {
  try {
    const u = new URL(url);
    return u.hostname.endsWith(".test") || u.pathname.startsWith("/__nivra_scripted__/")
      ? `/api/demo/image?url=${encodeURIComponent(url)}`
      : undefined;
  } catch {
    return undefined;
  }
}

export function jobCards(job: DiscoveryJob): ScanCardData[] {
  return (job.scan_log ?? []).map((e) => ({
    key: `${job.id}-${e.i}`,
    name: nameOf(e.url),
    result: e.result,
    phash: e.phash,
    diff: e.diff,
    distance: e.distance,
    exact: e.exact,
    label: e.label,
    thumb: demoThumb(e.url),
    scripted: e.scripted,
  }));
}

export default function LiveScan({
  jobIds,
  onFinished,
}: {
  jobIds: string[];
  onFinished?: (jobs: DiscoveryJob[]) => void;
}) {
  const [jobs, setJobs] = useState<Record<string, DiscoveryJob>>({});

  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    let announced = false;
    const tick = async () => {
      const results = await Promise.all(jobIds.map((id) => api.getDiscoveryJob(id).catch(() => null)));
      if (!live) return;
      setJobs((prev) => {
        const next = { ...prev };
        results.forEach((j) => { if (j) next[j.id] = j; });
        return next;
      });
      const finished = results.every((j) => !j || j.status === "done" || j.status === "failed");
      if (finished) {
        if (!announced) {
          announced = true;
          onFinished?.(results.filter((j): j is DiscoveryJob => j !== null));
        }
        return;
      }
      timer = setTimeout(tick, 900);
    };
    void tick();
    return () => { live = false; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- restart only when the job list changes
  }, [jobIds.join(",")]);

  return (
    <div className="stack">
      {jobIds.map((id) => {
        const j = jobs[id];
        return (
          <ScanView
            key={id}
            stage={j?.stage ?? "queued"}
            title={j?.page_title ? `${j.page_title} (${j.input_url})` : (j?.input_url ?? "Starting...")}
            cards={j ? jobCards(j) : []}
            error={j?.status === "failed" ? j.error_message : null}
          />
        );
      })}
    </div>
  );
}
