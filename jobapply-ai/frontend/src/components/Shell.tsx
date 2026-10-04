"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { cx, Spinner } from "./ui";

const NAV = [
  ["/dashboard", "nav.dashboard"], ["/profile", "nav.profile"], ["/cvs", "nav.cvs"], ["/jobs", "nav.jobs"], ["/matches", "nav.matches"],
  ["/applications", "nav.applications"], ["/email", "nav.email"], ["/settings", "nav.settings"], ["/privacy", "nav.privacy"],
] as const;

export default function Shell({ children }: { children: ReactNode }) {
  const { user, loading, logout } = useAuth();
  const { t, locale, setLocale } = useI18n();
  const path = usePathname();
  const router = useRouter();
  useEffect(() => { if (!loading && !user) router.replace("/login"); }, [loading, user, router]);
  if (loading || !user) return <Spinner />;
  const items: (readonly [string, string])[] = [...NAV];
  return (
    <div className="min-h-screen md:flex">
      <aside className="app-sidebar border-b md:min-h-screen md:w-64 md:border-b-0 md:border-r">
        <div className="flex items-center justify-between px-4 py-3 md:block">
          <Link href="/dashboard" className="app-brand">JobApply AI</Link>
          <div className="app-user truncate text-xs md:mt-2">{user.email}</div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2 md:block md:space-y-1 md:px-3 md:pb-3 md:pt-4 md:overflow-visible">
          {items.map(([href, key]) => (
            <Link key={href} href={href} aria-current={path === href || (href !== "/dashboard" && path.startsWith(href)) ? "page" : undefined} className="app-nav-link">{t(key)}</Link>
          ))}
        </nav>
        <div className="hidden space-y-2 px-4 py-3 md:block">
          <select aria-label="Language" className="input" value={locale} onChange={(e) => setLocale(e.target.value as "en" | "bn")}><option value="en">English</option><option value="bn">বাংলা</option></select>
          <button onClick={logout} className="app-logout">{t("nav.logout")}</button>
        </div>
      </aside>
      <main className="app-main flex-1 p-4 md:p-8">
        {!user.email_verified && <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Your email is not verified yet. You can prepare applications, but sending requires a verified email.</div>}
        <div className="mx-auto max-w-6xl space-y-4">{children}</div>
        <p className="app-disclaimer mx-auto mt-8 max-w-6xl text-xs">{t("disclaimer")}</p>
      </main>
    </div>
  );
}
