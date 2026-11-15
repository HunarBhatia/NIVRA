"use client";

import { EMBEDDING_MODEL_ID, loadEmbedder, type ProgressFn } from "./embedding";
import { gray32, sha256File } from "./image";
import { PHASH_ALGORITHM, phashFromGray } from "./phash";

export { UnreadableImage } from "./image";
export { EMBEDDING_MODEL_ID, embedderLoaded } from "./embedding";

export interface Fingerprints {
  sha256: string;
  phash: string;
  phash_algorithm: typeof PHASH_ALGORITHM;
  embedding?: { model: string; vector: number[] };
}

/**
 * Computes every fingerprint of an image ON THIS DEVICE. Only the returned
 * values are ever sent to Nivra's server - never the file.
 */
export async function fingerprintFile(
  file: Blob,
  opts: { embedding: boolean; onProgress?: ProgressFn } = { embedding: false },
): Promise<Fingerprints> {
  opts.onProgress?.({ status: "Reading the image" });
  const [sha256, gray] = await Promise.all([sha256File(file), gray32(file)]);
  const result: Fingerprints = {
    sha256,
    phash: phashFromGray(gray),
    phash_algorithm: PHASH_ALGORITHM,
  };
  if (opts.embedding) {
    const embedder = await loadEmbedder(opts.onProgress);
    opts.onProgress?.({ status: "Creating the AI similarity fingerprint" });
    result.embedding = { model: EMBEDDING_MODEL_ID, vector: await embedder.embed(file) };
  }
  return result;
}
