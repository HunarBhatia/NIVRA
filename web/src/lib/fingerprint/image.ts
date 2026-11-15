"use client";

// On-device image processing (D13). Everything here runs in the user's
// browser; the image itself is never uploaded anywhere.

const MAX_BYTES = 30 * 1024 * 1024;

export class UnreadableImage extends Error {}

/** SHA-256 of the exact file bytes, as 64 hex characters. */
export async function sha256File(file: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

async function decode(file: Blob): Promise<ImageBitmap> {
  if (file.size > MAX_BYTES) throw new UnreadableImage("That image is larger than 30 MB.");
  try {
    // "from-image" applies the photo's EXIF rotation, like Pillow's exif_transpose.
    return await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    throw new UnreadableImage("We couldn't read that image. Try a JPG, PNG or WebP file.");
  }
}

function canvas(w: number, h: number) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new UnreadableImage("Your browser can't process images here.");
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  return { c, ctx };
}

/**
 * The image as a 32x32 grid of luma values (BT.601), matching the Python
 * gray32() in backend/app/fingerprint/phash.py: transparency flattened onto
 * white, colour resized to 32x32, then converted to grey.
 */
export async function gray32(file: Blob): Promise<Float64Array> {
  const bitmap = await decode(file);
  try {
    // Halve the size step by step before the final 32x32 draw: one big jump
    // in a canvas skips pixels (aliasing); stepping approximates Pillow's
    // area-averaging LANCZOS resize much more closely.
    let w = bitmap.width;
    let h = bitmap.height;
    let src: CanvasImageSource = bitmap;
    while (w / 2 >= 64 && h / 2 >= 64) {
      w = Math.round(w / 2);
      h = Math.round(h / 2);
      const step = canvas(w, h);
      step.ctx.fillStyle = "#fff";
      step.ctx.fillRect(0, 0, w, h);
      step.ctx.drawImage(src, 0, 0, w, h);
      src = step.c;
    }
    const final = canvas(32, 32);
    final.ctx.fillStyle = "#fff";
    final.ctx.fillRect(0, 0, 32, 32);
    final.ctx.drawImage(src, 0, 0, 32, 32);
    const { data } = final.ctx.getImageData(0, 0, 32, 32);
    const gray = new Float64Array(32 * 32);
    for (let i = 0; i < gray.length; i++) {
      gray[i] = 0.299 * data[i * 4] + 0.587 * data[i * 4 + 1] + 0.114 * data[i * 4 + 2];
    }
    return gray;
  } finally {
    bitmap.close();
  }
}
