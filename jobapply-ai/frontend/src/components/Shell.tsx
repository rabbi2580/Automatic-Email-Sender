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
  const items: (readonly [string, string])[] = [...NAV, ...(user.role === "admin" ? [["/admin", "nav.admin"] as const] : [])];
  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-slate-200 bg-white md:min-h-screen md:w-60 md:border-b-0 md:border-r">
        <div className="flex items-center justify-between px-4 py-3 md:block">
          <Link href="/dashboard" className="text-lg font-bold text-brand-700">JobApply AI</Link>
          <div className="md:mt-1 md:text-xs text-xs text-slate-500 truncate">{user.email}</div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2 md:block md:space-y-1 md:overflow-visible">
          {items.map(([href, key]) => (
            <Link key={href} href={href} className={cx("block whitespace-nowrap rounded-md px-3 py-2 text-sm", path.startsWith(href) ? "bg-brand-50 font-semibold text-brand-700" : "text-slate-700 hover:bg-slate-100")}>{t(key)}</Link>
          ))}
        </nav>
        <div className="hidden space-y-2 px-4 py-3 md:block">
          <select aria-label="Language" className="input" value={locale} onChange={(e) => setLocale(e.target.value as "en" | "bn")}><option value="en">English</option><option value="bn">বাংলা</option></select>
          <button onClick={logout} className="text-sm text-slate-500 hover:text-slate-800">{t("nav.logout")}</button>
        </div>
      </aside>
      <main className="flex-1 p-4 md:p-6">
        {!user.email_verified && <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Your email is not verified yet. You can prepare applications, but sending requires a verified email.</div>}
        <div className="mx-auto max-w-6xl space-y-4">{children}</div>
        <p className="mx-auto mt-8 max-w-6xl text-xs text-slate-400">{t("disclaimer")}</p>
      </main>
    </div>
  );
}
