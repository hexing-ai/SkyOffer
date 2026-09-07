import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8001";
const demoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "1";

const nextConfig: NextConfig = {
  output: demoMode ? "export" : "standalone",
  distDir: demoMode ? ".next-demo" : ".next",
  basePath: process.env.NEXT_PUBLIC_BASE_PATH ?? "",
  trailingSlash: demoMode,
  deploymentId: process.env.DEPLOYMENT_VERSION,
  ...(!demoMode && { async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  } }),
};

export default nextConfig;
