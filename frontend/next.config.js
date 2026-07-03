/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // In dev, proxy /api/* to the FastAPI server on :8000 so the frontend
  // can call /api/analyze without CORS issues. In production, point this
  // at your deployed FastAPI URL via NEXT_PUBLIC_API_BASE_URL.
  async rewrites() {
    let apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
    // Render's fromService injects a bare hostname (no scheme); default to
    // https:// so the rewrite target is a valid absolute URL in production.
    if (apiBase && !/^https?:\/\//.test(apiBase)) {
      apiBase = `https://${apiBase}`;
    }
    return [
      { source: "/api/:path*", destination: `${apiBase}/api/:path*` },
    ];
  },
};

module.exports = nextConfig;
