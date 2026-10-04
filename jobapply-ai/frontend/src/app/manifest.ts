import type { MetadataRoute } from "next";
export default function manifest(): MetadataRoute.Manifest { return { name: "JobApply AI", short_name: "JobApply AI", description: "A smarter CV-based job application workspace", start_url: "/", display: "standalone", background_color: "#f7f9fc", theme_color: "#4f46e5", icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }] }; }
