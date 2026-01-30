import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
