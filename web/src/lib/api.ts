"use client";

import type { Fingerprints } from "./fingerprint";
import type {
  Account,
  CaseLink,
  CaseSummary,
  DiscoveredMatch,
  DiscoveryJob,
  Category,
  LinkStatus,
  MatchCheck,
  NivraCase,
  ProtectedImage,
} from "./types";

// Client for the Nivra backend (backend/app). Every call goes to /api/*,
// which Next.js proxies to FastAPI (see next.config.ts). The login session is
// an httpOnly cookie, so this code never sees or stores the session token.

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      ...init,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "We can't reach Nivra's server right now. Please try again shortly.");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const message =
      typeof body?.detail === "string"
        ? body.detail
        : res.status >= 500
          ? "We can't reach Nivra's server right now. Please try again shortly."
          : "Something went wrong. Please try again.";
    throw new ApiError(res.status, message);
  }
  return body as T;
}

const json = (method: string, data?: unknown): RequestInit => ({
  method,
  body: data === undefined ? undefined : JSON.stringify(data),
});

// ---------- Account ----------

/** Returns the logged-in account, or null if nobody is logged in. */
export async function getMe(): Promise<Account | null> {
  try {
    return await call<Account>("/auth/me");
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null;
    throw e;
  }
}

export const register = (passphrase: string) =>
  call<{ account_code: string }>("/auth/register", json("POST", { passphrase }));

export const login = (accountCode: string, passphrase: string) =>
  call<Account>("/auth/login", json("POST", { account_code: accountCode, passphrase }));

export const logout = () => call<void>("/auth/logout", json("POST"));

export const deleteAccount = (passphrase: string) =>
  call<void>("/account", json("DELETE", { passphrase }));

// ---------- Cases ----------

export const listCases = () => call<CaseSummary[]>("/cases");

export const getCase = (id: string) => call<NivraCase>(`/cases/${encodeURIComponent(id)}`);

export const createCase = (input: {
  category: Category;
  self_taken: boolean | null;
  display_name: string;
  urls: string[];
}) => call<NivraCase>("/cases", json("POST", input));

export const updateCase = (id: string, displayName: string) =>
  call<NivraCase>(`/cases/${encodeURIComponent(id)}`, json("PATCH", { display_name: displayName }));

export const deleteCase = (id: string) =>
  call<void>(`/cases/${encodeURIComponent(id)}`, json("DELETE"));

export const addLinks = (caseId: string, urls: string[]) =>
  call<NivraCase>(`/cases/${encodeURIComponent(caseId)}/links`, json("POST", { urls }));

export const changeStatus = (linkId: string, status: LinkStatus, note?: string) =>
  call<CaseLink>(`/links/${encodeURIComponent(linkId)}/status`, json("POST", { status, note }));

/** Prototype only - the server refuses this when prototype tools are off. */
export const simulateDeadline = (linkId: string) =>
  call<CaseLink>(`/links/${encodeURIComponent(linkId)}/simulate-deadline`, json("POST"));

// ---------- Helpers ----------

/** True when a reported link has passed its platform's response deadline. */
export function isOverdue(link: CaseLink, expectedHours: number) {
  if (link.status !== "reported" || !link.reported_at) return false;
  if (link.deadline_override) return true;
  return Date.now() - new Date(link.reported_at).getTime() > expectedHours * 3_600_000;
}

// ---------- Protected images (phase 3) ----------
// Only fingerprints are ever sent (D13). See lib/fingerprint.

export const CONSENT_VERSION = "2026-11-v1";

export const listImages = () => call<ProtectedImage[]>("/images");

export const registerImage = (input: {
  label: string;
  fingerprints: Fingerprints;
}) =>
  call<ProtectedImage>(
    "/images",
    json("POST", {
      label: input.label,
      consent: { subject_is_adult: true, is_subject_or_authorised: true },
      consent_version: CONSENT_VERSION,
      fingerprints: input.fingerprints,
    }),
  );

export const updateImage = (id: string, patch: { label?: string; status?: "active" | "paused" }) =>
  call<ProtectedImage>(`/images/${encodeURIComponent(id)}`, json("PATCH", patch));

export const setImageEmbedding = (id: string, embedding: { model: string; vector: number[] }) =>
  call<ProtectedImage>(`/images/${encodeURIComponent(id)}/embedding`, json("PUT", embedding));

export const revokeImage = (id: string) =>
  call<void>(`/images/${encodeURIComponent(id)}`, json("DELETE"));

export const checkCopy = (fp: Omit<Fingerprints, "phash_algorithm">) =>
  call<MatchCheck>(
    "/images/check",
    json("POST", { sha256: fp.sha256, phash: fp.phash, embedding: fp.embedding }),
  );

// ---------- Discovery (phase 4) ----------

export const createDiscoveryJob = (url: string) =>
  call<DiscoveryJob>("/discovery/jobs", json("POST", { url }));

export const listDiscoveryJobs = () => call<DiscoveryJob[]>("/discovery/jobs");

export const getDiscoveryJob = (id: string) =>
  call<DiscoveryJob>(`/discovery/jobs/${encodeURIComponent(id)}`);

export const listMatches = () => call<DiscoveredMatch[]>("/matches");

export const reviewMatch = (id: string, decision: "confirmed" | "rejected" | "pending") =>
  call<DiscoveredMatch>(`/matches/${encodeURIComponent(id)}/review`, json("POST", { decision }));

export const addMatchToCase = (id: string, target: { case_id?: string; category?: Category }) =>
  call<{ case_id: string; link_id: string }>(
    `/matches/${encodeURIComponent(id)}/add-to-case`,
    json("POST", target),
  );
