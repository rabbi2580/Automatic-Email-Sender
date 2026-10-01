"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";

export type Locale = "en" | "bn";

const dict: Record<Locale, Record<string, string>> = {
  en: {
    "nav.dashboard": "Dashboard", "nav.profile": "My Profile", "nav.cvs": "My CVs", "nav.jobs": "Find / Add Jobs", "nav.matches": "Job Matches",
    "nav.applications": "Applications", "nav.email": "Email", "nav.settings": "Settings", "nav.privacy": "Privacy", "nav.admin": "Admin", "nav.logout": "Sign out",
    "common.save": "Save", "common.cancel": "Cancel", "common.loading": "Loading…", "common.delete": "Delete", "common.retry": "Retry", "common.next": "Next", "common.back": "Back",
    "disclaimer": "AI-assisted drafts. Review everything before you approve. Nothing is sent without your explicit confirmation.",
  },
  bn: {
    "nav.dashboard": "ড্যাশবোর্ড", "nav.profile": "আমার প্রোফাইল", "nav.cvs": "আমার সিভি", "nav.jobs": "চাকরি খুঁজুন / যোগ করুন", "nav.matches": "জবের মিল",
    "nav.applications": "আবেদনসমূহ", "nav.email": "ইমেইল", "nav.settings": "সেটিংস", "nav.privacy": "গোপনীয়তা", "nav.admin": "অ্যাডমিন", "nav.logout": "সাইন আউট",
    "common.save": "সংরক্ষণ", "common.cancel": "বাতিল", "common.loading": "লোড হচ্ছে…", "common.delete": "মুছুন", "common.retry": "আবার চেষ্টা", "common.next": "পরবর্তী", "common.back": "পেছনে",
    "disclaimer": "এআই-সহায়ক খসড়া। অনুমোদনের আগে সবকিছু যাচাই করুন। আপনার স্পষ্ট নিশ্চিতকরণ ছাড়া কিছুই পাঠানো হবে না।",
  },
};

const Ctx = createContext<{ locale: Locale; setLocale: (l: Locale) => void; t: (k: string) => string }>({ locale: "en", setLocale: () => {}, t: (k) => k });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setL] = useState<Locale>("en");
  useEffect(() => { try { const l = localStorage.getItem("jaa_locale"); if (l === "bn" || l === "en") setL(l); } catch { /* ignore */ } }, []);
  const setLocale = (l: Locale) => { setL(l); try { localStorage.setItem("jaa_locale", l); } catch { /* ignore */ } };
  const t = (k: string) => dict[locale][k] ?? dict.en[k] ?? k;
  return <Ctx.Provider value={{ locale, setLocale, t }}>{children}</Ctx.Provider>;
}
export const useI18n = () => useContext(Ctx);
