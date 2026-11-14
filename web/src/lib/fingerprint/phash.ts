// Perceptual hash, algorithm "phash-dct-v1".
// MUST stay identical to backend/app/fingerprint/phash.py. Both are checked
// against backend/tests/fixtures/phash_vectors.json
// (run: node --experimental-strip-types scripts/check-phash.ts).
//
// Pure maths only (no browser APIs) so the check script can run it in Node.

export const PHASH_ALGORITHM = "phash-dct-v1";
const SIZE = 32;
const LOW = 8;

// DCT-II basis: C[k][n] = cos(pi * (2n + 1) * k / (2N)).
const DCT: number[][] = Array.from({ length: SIZE }, (_, k) =>
  Array.from({ length: SIZE }, (_, n) => Math.cos((Math.PI * (2 * n + 1) * k) / (2 * SIZE))),
);

/** gray: 32*32 luma values, row-major. Returns 16 hex characters. */
export function phashFromGray(gray: ArrayLike<number>): string {
  if (gray.length !== SIZE * SIZE) throw new Error("expected a 32x32 grey grid");

  // dct = C @ G @ C^T, but only the top-left 8x8 block is needed.
  // tmp = C[0..8] @ G  (8 x 32)
  const tmp: number[][] = [];
  for (let k = 0; k < LOW; k++) {
    const row = new Array<number>(SIZE).fill(0);
    for (let n = 0; n < SIZE; n++) {
      const c = DCT[k][n];
      for (let j = 0; j < SIZE; j++) row[j] += c * gray[n * SIZE + j];
    }
    tmp.push(row);
  }
  // low = tmp @ C[0..8]^T  (8 x 8)
  const low: number[] = [];
  for (let k = 0; k < LOW; k++) {
    for (let l = 0; l < LOW; l++) {
      let s = 0;
      for (let j = 0; j < SIZE; j++) s += tmp[k][j] * DCT[l][j];
      low.push(s);
    }
  }

  const sorted = [...low].sort((a, b) => a - b);
  const median = (sorted[31] + sorted[32]) / 2;
  // Same noise margin as the Python version: values equal to the median in
  // exact maths must not flip on floating-point noise.
  const eps = 1e-9 * Math.max(...low.map(Math.abs));

  let hex = "";
  for (let i = 0; i < 64; i += 4) {
    let nibble = 0;
    for (let b = 0; b < 4; b++) nibble = (nibble << 1) | (low[i + b] > median + eps ? 1 : 0);
    hex += nibble.toString(16);
  }
  return hex;
}

/** Number of differing bits between two 64-bit hex hashes (0-64). */
export function hamming(a: string, b: string): number {
  let x = BigInt(`0x${a}`) ^ BigInt(`0x${b}`);
  let count = 0;
  while (x > BigInt(0)) {
    count += Number(x & BigInt(1));
    x >>= BigInt(1);
  }
  return count;
}
