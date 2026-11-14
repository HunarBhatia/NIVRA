"use client";

// Evidence locker encryption (PROJECT_DETAILS.txt 18.6, decision D9).
//
// - The key is derived HERE, in the browser, from the user's passphrase and a
//   random salt: PBKDF2-SHA256, 600,000 rounds -> AES-GCM 256-bit key.
// - The key is non-extractable and lives only in memory for this page; it is
//   never sent anywhere. Locking, closing the tab or Quick exit forgets it.
// - Each file and each description is encrypted with AES-GCM and a fresh
//   random 12-byte IV. The server stores only ciphertext.
// - A known value ("key check") encrypted at setup lets us tell a wrong
//   passphrase from a right one without the server knowing either.
//
// If the passphrase is lost, the evidence cannot be recovered - by anyone.

const ITERATIONS = 600_000;
const CHECK_TEXT = "nivra-evidence-check-v1";
const enc = new TextEncoder();
const dec = new TextDecoder();

export function toB64(bytes: Uint8Array): string {
  let s = "";
  const chunk = 0x8000; // avoid call-stack limits on big files
  for (let i = 0; i < bytes.length; i += chunk) {
    s += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(s);
}

export function fromB64(b64: string): Uint8Array {
  const s = atob(b64);
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}

export async function deriveKey(passphrase: string, saltB64: string): Promise<CryptoKey> {
  const base = await crypto.subtle.importKey("raw", enc.encode(passphrase), "PBKDF2", false, [
    "deriveKey",
  ]);
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", hash: "SHA-256", salt: fromB64(saltB64) as BufferSource, iterations: ITERATIONS },
    base,
    { name: "AES-GCM", length: 256 },
    false, // non-extractable: the raw key can't be read back out
    ["encrypt", "decrypt"],
  );
}

export async function encryptBytes(key: CryptoKey, data: Uint8Array): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, data as BufferSource),
  );
  const out = new Uint8Array(iv.length + ct.length);
  out.set(iv);
  out.set(ct, iv.length);
  return toB64(out);
}

export async function decryptBytes(key: CryptoKey, b64: string): Promise<Uint8Array> {
  const all = fromB64(b64);
  const pt = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: all.subarray(0, 12) as BufferSource },
    key,
    all.subarray(12) as BufferSource,
  );
  return new Uint8Array(pt);
}

export async function encryptJson(key: CryptoKey, value: unknown): Promise<string> {
  return encryptBytes(key, enc.encode(JSON.stringify(value)));
}

export async function decryptJson<T>(key: CryptoKey, b64: string): Promise<T> {
  return JSON.parse(dec.decode(await decryptBytes(key, b64))) as T;
}

export async function sha256Hex(data: Uint8Array): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", data as BufferSource);
  return Array.from(new Uint8Array(d), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** First-time setup: returns what the server stores, plus the key for this session. */
export async function newLocker(passphrase: string) {
  const salt = toB64(crypto.getRandomValues(new Uint8Array(16)));
  const key = await deriveKey(passphrase, salt);
  const keyCheck = await encryptBytes(key, enc.encode(CHECK_TEXT));
  return { salt, keyCheck, key };
}

/** Returns the key if the passphrase is right, or null if it's wrong. */
export async function openLocker(
  passphrase: string,
  salt: string,
  keyCheck: string,
): Promise<CryptoKey | null> {
  const key = await deriveKey(passphrase, salt);
  try {
    const text = dec.decode(await decryptBytes(key, keyCheck));
    return text === CHECK_TEXT ? key : null;
  } catch {
    return null; // AES-GCM authentication fails with the wrong key
  }
}

// What we encrypt alongside each item (the server can't read any of it).
export interface EvidenceMeta {
  caption: string;
  text?: string; // notes, account names, messages
  filename?: string;
  mime?: string;
  size?: number;
  sha256?: string; // of the ORIGINAL file, for evidence reports
}
