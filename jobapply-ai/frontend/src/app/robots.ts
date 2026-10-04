import type { MetadataRoute } from "next";
export default function robots(): MetadataRoute.Robots {
  const site = process.env.NEXT_PUBLIC_SITE_URL || "https://yourdomain.com";
  return { rules: [{ userAgent: "*", allow: ["/", "/login", "/register"], disallow: ["/api/", "/admin/", "/dashboard/", "/profile/", "/cvs/", "/jobs/", "/matches/", "/applications/", "/email/", "/settings/", "/privacy/", "/uploads/"] }], sitemap: `${site}/sitemap.xml` };
}
