import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // NOTE: "standalone" requires `node .next/standalone/server.js` to start,
  // but our Procfile uses `npm start` (next start). Removed to avoid mismatch.
  // output: "standalone",
  experimental: {
    // Enable Server Actions
  },
  async rewrites() {
    return [
      {
        source: "/api/orchestrator/:path*",
        destination: `${process.env.ORCHESTRATOR_API_URL || "http://localhost:8502"}/:path*`,
      },
    ];
  },
};

export default nextConfig;
