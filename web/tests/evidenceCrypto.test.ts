// Tests for the evidence locker's in-browser encryption (section 18.10).
// Run: npm test   (Node's built-in test runner; same Web Crypto as browsers)

import assert from "node:assert/strict";
import { test } from "node:test";
import {
  decryptBytes,
  decryptJson,
  encryptBytes,
  encryptJson,
  fromB64,
  newLocker,
  openLocker,
  sha256Hex,
  toB64,
} from "../src/lib/evidenceCrypto.ts";

const PASS = "a long test passphrase";

test("encrypt then decrypt returns the original bytes", async () => {
  const { key } = await newLocker(PASS);
  const data = new TextEncoder().encode("screenshot bytes");
  const back = await decryptBytes(key, await encryptBytes(key, data));
  assert.deepEqual(back, data);
});

test("JSON metadata round-trips", async () => {
  const { key } = await newLocker(PASS);
  const meta = { caption: "Who posted it", text: "@someone", sha256: "ab".repeat(32) };
  assert.deepEqual(await decryptJson(key, await encryptJson(key, meta)), meta);
});

test("ciphertext is fresh each time and adds exactly IV + tag (28 bytes)", async () => {
  const { key } = await newLocker(PASS);
  const data = new Uint8Array(1000);
  const a = await encryptBytes(key, data);
  const b = await encryptBytes(key, data);
  assert.notEqual(a, b); // random IV every time
  assert.equal(fromB64(a).length, 1000 + 12 + 16);
});

test("the right passphrase opens the locker, a wrong one doesn't", async () => {
  const { salt, keyCheck } = await newLocker(PASS);
  assert.ok(await openLocker(PASS, salt, keyCheck));
  assert.equal(await openLocker("wrong passphrase", salt, keyCheck), null);
});

test("a key from a wrong passphrase can't decrypt evidence", async () => {
  const { salt, key } = await newLocker(PASS);
  const ct = await encryptBytes(key, new TextEncoder().encode("secret"));
  const { deriveKey } = await import("../src/lib/evidenceCrypto.ts");
  const wrong = await deriveKey("wrong passphrase", salt);
  await assert.rejects(decryptBytes(wrong, ct));
});

test("tampered ciphertext is rejected (AES-GCM authentication)", async () => {
  const { key } = await newLocker(PASS);
  const bytes = fromB64(await encryptBytes(key, new TextEncoder().encode("evidence")));
  bytes[bytes.length - 1] ^= 1;
  await assert.rejects(decryptBytes(key, toB64(bytes)));
});

test("base64 helpers handle large files (chunked)", () => {
  const big = new Uint8Array(1_500_000).map((_, i) => i % 251);
  assert.deepEqual(fromB64(toB64(big)), big);
});

test("SHA-256 matches the standard test vector", async () => {
  assert.equal(
    await sha256Hex(new TextEncoder().encode("abc")),
    "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
  );
});
