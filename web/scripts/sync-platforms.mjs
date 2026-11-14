// Copies the shared platform directory into the website before dev/build.
// Source of truth: ../shared/platforms.json (also read by the backend).
// The backend test suite fails if the two copies ever differ.
import { copyFileSync, mkdirSync } from "node:fs";

const src = new URL("../../shared/platforms.json", import.meta.url);
const destDir = new URL("../src/data/", import.meta.url);
mkdirSync(destDir, { recursive: true });
copyFileSync(src, new URL("platforms.json", destDir));
console.log("platforms.json synced from shared/");
