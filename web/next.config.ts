import type { NextConfig } from "next";

// Where the FastAPI backend runs. The browser only ever talks to this Next.js
// site; /api/* is proxied server-side, so the login cookie stays first-party
// and no CORS is needed.
const API_URL = process.env.NIVRA_API_URL ?? "http://127.0.0.1:8000";
const isDev = process.env.NODE_ENV !== "production";

// Content Security Policy (section 21.4). Scripts and data may only come from
// this site, plus what the optional on-device AI fingerprint needs: the model
// files from Hugging Face and ONNX Runtime's WebAssembly from jsDelivr.
// 'unsafe-inline' scripts are needed by Next.js's bootstrap without nonces;
// 'unsafe-eval' only in development (React dev tools / fast refresh).
const csp = [
  "default-src 'self'",
  // blob: - ONNX Runtime starts part of itself from a blob: URL it creates
  // (found in testing: without it the AI fingerprint fails). Only this page's
  // own code can create blob: URLs.
  `script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' blob: https://cdn.jsdelivr.net${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  `connect-src 'self' https://huggingface.co https://*.huggingface.co https://*.hf.co https://cdn.jsdelivr.net${isDev ? " ws: wss:" : ""}`,
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  // Never tell other sites which Nivra page someone came from.
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  ...(isDev ? [] : [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }]),
];

const nextConfig: NextConfig = {
  // Self-contained server build for the Docker image (deploy/).
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
