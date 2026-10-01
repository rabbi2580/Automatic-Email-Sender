"use client";
import { useEffect } from "react";
import { tokens } from "@/lib/api";

// Google sign-in returns tokens in the URL fragment (never sent to a server or logged).
export default function Callback() {
  useEffect(() => {
    const p = new URLSearchParams(location.hash.replace(/^#/, ""));
    const a = p.get("access_token"), r = p.get("refresh_token");
    history.replaceState(null, "", location.pathname);
    if (a && r) { tokens.set(a, r); location.href = "/dashboard"; } else location.href = "/login";
  }, []);
  return <p className="p-6 text-sm text-slate-500">Signing you in…</p>;
}
