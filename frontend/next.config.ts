import path from "node:path";
import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

const currentDirectory = path.dirname(fileURLToPath(import.meta.url));
const internalApiProxyUrl = process.env.INTERNAL_API_PROXY_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  turbopack: {
    root: currentDirectory,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${internalApiProxyUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
