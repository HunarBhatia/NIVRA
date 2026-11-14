import type { NextConfig } from "next";

// Where the FastAPI backend runs. The browser only ever talks to this Next.js
// site; /api/* is proxied server-side, so the login cookie stays first-party
// and no CORS is needed.
const API_URL = process.env.NIVRA_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
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
