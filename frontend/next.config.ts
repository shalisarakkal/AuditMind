import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The Imports page became Uploads (2026-09-30): old links and bookmarks.
  async redirects() {
    return [{ source: "/imports", destination: "/uploads", permanent: false }];
  },
};

export default nextConfig;
