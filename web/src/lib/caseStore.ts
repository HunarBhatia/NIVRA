"use client";

import type { CaseLink, Category, LinkStatus, NivraCase } from "./types";
import { normaliseUrl, resolvePlatform } from "./platforms";

// PROTOTYPE STORAGE. Cases are kept in this browser's localStorage so the
// prototype works without a server. The real product stores links on the
// server (decision D9). Never treat this as the production design.

const STORE_KEY = "nivra.cases.v1";
const OPEN_KEY = "nivra.openCase";

function readAll(): Record<string, NivraCase> {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    return raw ? (JSON.parse(raw) as Record<string, NivraCase>) : {};
  } catch {
    return {};
  }
}

function writeAll(all: Record<string, NivraCase>) {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(all));
  } catch {
    // Storage blocked (private mode etc.). The prototype keeps going in memory.
  }
}

const ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"; // no 0/O or 1/I confusion

function randomChars(n: number) {
  const bytes = crypto.getRandomValues(new Uint8Array(n));
  return Array.from(bytes, (b) => ALPHABET[b % ALPHABET.length]).join("");
}

export function newCaseId() {
  return `NV-${randomChars(4)}-${randomChars(4)}`;
}

function newId() {
  return randomChars(10);
}

function toHex(buf: ArrayBuffer) {
  return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Slow hash of the passphrase (PBKDF2, 150k rounds) so it is never stored as-is. */
async function hashPassphrase(passphrase: string, saltHex: string) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey("raw", enc.encode(passphrase), "PBKDF2", false, [
    "deriveBits",
  ]);
  const salt = new Uint8Array(saltHex.match(/../g)!.map((h) => parseInt(h, 16)));
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt, iterations: 150_000 },
    key,
    256,
  );
  return toHex(bits);
}

export function makeLink(rawUrl: string): CaseLink | null {
  const url = normaliseUrl(rawUrl);
  if (!url) return null;
  const now = new Date().toISOString();
  return {
    id: newId(),
    url,
    platformId: resolvePlatform(url)?.id ?? null,
    status: "found",
    events: [{ at: now, status: "found", note: "Link added" }],
  };
}

export async function createCase(input: {
  category: Category;
  selfTaken: boolean | null;
  displayName: string;
  passphrase: string;
  urls: string[];
}): Promise<NivraCase> {
  const salt = toHex(crypto.getRandomValues(new Uint8Array(16)).buffer);
  const all = readAll();
  let id = newCaseId();
  while (all[id]) id = newCaseId();

  const c: NivraCase = {
    id,
    createdAt: new Date().toISOString(),
    category: input.category,
    selfTaken: input.selfTaken,
    displayName: input.displayName,
    salt,
    passHash: await hashPassphrase(input.passphrase, salt),
    links: input.urls.map(makeLink).filter((l): l is CaseLink => l !== null),
  };
  all[id] = c;
  writeAll(all);
  setOpenCase(id);
  return c;
}

export async function unlockCase(id: string, passphrase: string): Promise<NivraCase | null> {
  const c = readAll()[id.trim().toUpperCase()];
  if (!c) return null;
  const hash = await hashPassphrase(passphrase, c.salt);
  if (hash !== c.passHash) return null;
  setOpenCase(c.id);
  return c;
}

export function getCase(id: string): NivraCase | null {
  return readAll()[id] ?? null;
}

export function saveCase(c: NivraCase) {
  const all = readAll();
  all[c.id] = c;
  writeAll(all);
}

export function deleteCase(id: string) {
  const all = readAll();
  delete all[id];
  writeAll(all);
  closeCase();
}

/** The open case lives in sessionStorage, so closing the tab locks it again. */
export function setOpenCase(id: string) {
  try {
    sessionStorage.setItem(OPEN_KEY, id);
  } catch {}
}

export function getOpenCaseId(): string | null {
  try {
    return sessionStorage.getItem(OPEN_KEY);
  } catch {
    return null;
  }
}

export function closeCase() {
  try {
    sessionStorage.removeItem(OPEN_KEY);
  } catch {}
}

export function withStatus(link: CaseLink, status: LinkStatus, note?: string): CaseLink {
  const at = new Date().toISOString();
  return {
    ...link,
    status,
    reportedAt: status === "reported" ? at : link.reportedAt,
    deadlineOverride: status === "reported" ? false : link.deadlineOverride,
    events: [...link.events, { at, status, note }],
  };
}

/** True when a reported link has passed its platform's response deadline. */
export function isOverdue(link: CaseLink, expectedHours: number) {
  if (link.status !== "reported" || !link.reportedAt) return false;
  if (link.deadlineOverride) return true;
  return Date.now() - new Date(link.reportedAt).getTime() > expectedHours * 3_600_000;
}
