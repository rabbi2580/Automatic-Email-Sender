import "./globals.css";
import type { Metadata } from "next";
import { AuthProvider } from "@/lib/auth";
import { I18nProvider } from "@/lib/i18n";
import { ToastProvider } from "@/components/ui";

export const metadata: Metadata = { title: "JobApply AI", description: "Upload your CV, add jobs, review tailored applications, approve and send." };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body><I18nProvider><AuthProvider><ToastProvider>{children}</ToastProvider></AuthProvider></I18nProvider></body>
    </html>
  );
}
