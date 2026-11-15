"use client";

// AI similarity fingerprint ("embedding"), computed on this device.
//
// Model: CLIP ViT-B/32 vision encoder, 8-bit quantised, run by
// transformers.js (ONNX Runtime Web). The model files (~90 MB) download once
// from Hugging Face and are cached by the browser; the IMAGE never leaves
// the device. The model sits behind this small interface so it can be
// swapped later (the server records the model name with every embedding).

export const EMBEDDING_MODEL_ID = "clip-vit-base-patch32-q8"; // name the server knows
const HF_REPO = "Xenova/clip-vit-base-patch32";

export interface Embedder {
  embed(file: Blob): Promise<number[]>;
}

export type ProgressFn = (info: { status: string; progress?: number }) => void;

let loading: Promise<Embedder> | null = null;

/** Loads the model once per page (downloading it the first time). */
export function loadEmbedder(onProgress?: ProgressFn): Promise<Embedder> {
  if (!loading) {
    loading = (async () => {
      // Imported lazily so the ~1 MB library only loads when someone opts in.
      const { AutoProcessor, CLIPVisionModelWithProjection, RawImage, env } = await import(
        "@huggingface/transformers"
      );
      env.allowLocalModels = false;
      const progress_callback = (p: { status: string; progress?: number }) =>
        onProgress?.({ status: p.status, progress: p.progress });
      const processor = await AutoProcessor.from_pretrained(HF_REPO, { progress_callback });
      const model = await CLIPVisionModelWithProjection.from_pretrained(HF_REPO, {
        dtype: "q8",
        progress_callback,
      });
      return {
        async embed(file: Blob) {
          const image = await RawImage.fromBlob(file);
          const inputs = await processor(image);
          const { image_embeds } = await model(inputs);
          const v = Array.from(image_embeds.data as Float32Array);
          const norm = Math.hypot(...v) || 1;
          return v.map((x) => x / norm);
        },
      };
    })().catch((e) => {
      loading = null; // allow a retry after a failed download
      throw e;
    });
  }
  return loading;
}

export function embedderLoaded() {
  return loading !== null;
}
