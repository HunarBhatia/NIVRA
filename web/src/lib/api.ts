"use client";

import type { Account, CaseLink, CaseSummary, Category, LinkStatus, NivraCase } from "./types";

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
