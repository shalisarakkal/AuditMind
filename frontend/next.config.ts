import type { NextConfig } from "next";

// The backend, which the app reaches through this server at /api, so pages
// and API share one address and the session cookie (HttpOnly, SameSite=Strict)
// works. 127.0.0.1, not localhost: on Windows localhost tries IPv6 first,
// where the backend doesn't listen, costing ~2 s per new connection.
// In production a reverse proxy in front (e.g. nginx) should send /api to the
// backend itself, with the visitor's address (X-Forwarded-For): passed on
// from here, every request looks like it comes from this server.
const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Dedicated acceptance builds must not replace a running demo's chunks.
  distDir: process.env.AUDITMIND_ISOLATED_BUILD === "1" ? ".next-acceptance" : ".next",
  reactStrictMode: true,
  // Next's dev badge sits bottom-left by default, over the sidebar's account
  // menu.
  devIndicators: { position: "bottom-right" },
  // The Imports page became Uploads (2026-09-30): old links and bookmarks.
  async redirects() {
    return [{ source: "/imports", destination: "/uploads", permanent: false }];
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
  experimental: {
    // An upload of up to 10 MB is processed during the request (the backend's
    // IMPORT_SYNC_MAX_BYTES), and 100 MB ones take a while to send: more than
    // the 30 s Next allows by default.
    proxyTimeout: 10 * 60 * 1000,
    // Next keeps a copy of each request body it passes on, up to this size;
    // a larger upload stalls (it's 10 MB by default). Above the backend's
    // own upload limit (IMPORT_MAX_BYTES), which refuses bigger files itself.
    proxyClientMaxBodySize: "2gb",
  },
};

export default nextConfig;
