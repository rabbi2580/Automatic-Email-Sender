/** @type {import('next').NextConfig} */
const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
];
const nextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/backend/:path*", destination: "http://127.0.0.1:8000/api/v1/:path*" }];
  },
  async headers() { return [
    { source: "/(.*)", headers: securityHeaders },
    { source: "/(app)(.*)", headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow, noarchive" }] },
    { source: "/admin(.*)", headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow, noarchive" }] },
  ]; },
};
export default nextConfig;
