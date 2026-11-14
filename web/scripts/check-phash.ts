// Checks that the TypeScript pHash matches the Python one on shared vectors.
// Run from web/:  node --experimental-strip-types scripts/check-phash.ts

import { readFileSync } from "node:fs";
import { PHASH_ALGORITHM, phashFromGray } from "../src/lib/fingerprint/phash.ts";

const fixture = JSON.parse(
  readFileSync(new URL("../../backend/tests/fixtures/phash_vectors.json", import.meta.url), "utf8"),
) as { algorithm: string; vectors: { name: string; gray: number[]; phash: string }[] };

if (fixture.algorithm !== PHASH_ALGORITHM) {
  console.error(`Algorithm mismatch: fixture ${fixture.algorithm}, TS ${PHASH_ALGORITHM}`);
  process.exit(1);
}

let failed = 0;
for (const v of fixture.vectors) {
  const got = phashFromGray(v.gray);
  const ok = got === v.phash;
  if (!ok) failed++;
  console.log(`${ok ? "ok  " : "FAIL"} ${v.name}: expected ${v.phash}, got ${got}`);
}
if (failed) {
  console.error(`${failed} vector(s) differ between Python and TypeScript`);
  process.exit(1);
}
console.log(`All ${fixture.vectors.length} vectors match.`);
