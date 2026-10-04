import "./globals.css";
import type { Metadata } from "next";
import { AuthProvider } from "@/lib/auth";
import { I18nProvider } from "@/lib/i18n";
import { ThemeProvider } from "@/lib/theme";
import { ToastProvider } from "@/components/ui";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "https://yourdomain.com"),
  title: { default: "JobApply AI | Smarter CV-based job applications", template: "%s | JobApply AI" },
  description: "Parse your CV, build a complete profile, match jobs, and prepare tailored applications with control at every step.",
  alternates: { canonical: "/" },
  openGraph: { type: "website", siteName: "JobApply AI", title: "JobApply AI | Smarter CV-based job applications", description: "Turn one CV into a clearer, more confident application workflow.", images: [{ url: "/og-image.svg", width: 1200, height: 630, alt: "JobApply AI" }] },
  twitter: { card: "summary_large_image", title: "JobApply AI | Smarter CV-based job applications", description: "Parse your CV, match jobs, and prepare applications with confidence.", images: ["/og-image.svg"] },
  icons: { icon: "/icon.svg", apple: "/icon.svg" },
  manifest: "/manifest.webmanifest",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body><ThemeProvider><I18nProvider><AuthProvider><ToastProvider>{children}</ToastProvider></AuthProvider></I18nProvider></ThemeProvider></body>
    </html>
  );
}
