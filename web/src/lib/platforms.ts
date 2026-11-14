import data from "@/data/platforms.json";
import type { Platform } from "./types";

// The Platform Directory (blueprint 10.6). Loaded from the shared file
// ../../shared/platforms.json (copied to src/data by scripts/sync-platforms.mjs),
// which the backend reads too - one source of truth (section 18.3).
// PROTOTYPE DATA: nothing is marked verified until a person checks it.

interface RawPlatform {
  id: string;
  name: string;
  owner: string | null;
  domains: string[];
  expected_hours: number;
  mechanisms: { kind: "form" | "email" | "in-app"; label: string; target?: string }[];
  required_info: string[];
  required_evidence: string[];
  submission_steps: string[];
  status_tracking: "email" | "in_app" | "ticket" | "none";
  tracking_note: string | null;
  notes: string | null;
  verified: boolean;
  last_verified: string | null;
}

export const PLATFORMS: Platform[] = (data.platforms as RawPlatform[]).map((p) => ({
  id: p.id,
  name: p.name,
  owner: p.owner ?? undefined,
  domains: p.domains,
  expectedHours: p.expected_hours,
  channels: p.mechanisms,
  inAppSteps: p.submission_steps,
  notes: p.notes ?? undefined,
  requiredInfo: p.required_info,
  requiredEvidence: p.required_evidence,
  statusTracking: p.status_tracking,
  trackingNote: p.tracking_note ?? undefined,
  verified: p.verified,
  lastVerified: p.last_verified,
}));

/** Google Search de-indexing: useful for every link, even when a site refuses. */
export const GOOGLE_DEINDEX_URL = "https://support.google.com/websearch/answer/6302812";
export const STOPNCII_URL = "https://stopncii.org/";
export const TAKE_IT_DOWN_URL = "https://takeitdown.ncmec.org/";
export const CYBERCRIME_URL = "https://cybercrime.gov.in/";
export const CLOUDFLARE_ABUSE_URL = "https://abuse.cloudflare.com/";

export function getPlatform(id: string | null | undefined): Platform | undefined {
  return PLATFORMS.find((p) => p.id === id);
}

/** Returns the bare hostname without "www.", or null if the text isn't a URL. */
export function hostnameOf(raw: string): string | null {
  const text = raw.trim();
  if (!text) return null;
  try {
    const url = new URL(/^https?:\/\//i.test(text) ? text : `https://${text}`);
    if (!url.hostname.includes(".")) return null;
    return url.hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    return null;
  }
}

/** Normalises a pasted link so it always starts with https:// */
export function normaliseUrl(raw: string): string | null {
  const text = raw.trim();
  if (!hostnameOf(text)) return null;
  return /^https?:\/\//i.test(text) ? text : `https://${text}`;
}

/**
 * Splits pasted text into link candidates: one per line (or comma). A line is
 * only split on spaces when every piece looks like a link, so "not a link"
 * stays one entry instead of three.
 */
export function splitLinks(text: string): string[] {
  return text
    .split(/[\n,]+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .flatMap((line) => {
      const parts = line.split(/\s+/);
      return parts.length > 1 && parts.every((p) => hostnameOf(p)) ? parts : [line];
    });
}

/** Finds the platform for a URL, matching subdomains too (m.facebook.com -> facebook). */
export function resolvePlatform(raw: string): Platform | null {
  const host = hostnameOf(raw);
  if (!host) return null;
  return (
    PLATFORMS.find((p) => p.domains.some((d) => host === d || host.endsWith(`.${d}`))) ?? null
  );
}
