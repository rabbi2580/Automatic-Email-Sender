"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";

function Inner() {
  const token = useSearchParams().get("token");
  const [state, setState] = useState<"working" | "ok" | "bad">("working");
  useEffect(() => {
    if (!token) { setState("bad"); return; }
    api("/auth/verify-email", { body: { token }, auth: false }).then(() => setState("ok")).catch(() => setState("bad"));
  }, [token]);
  return (
    <main className="mx-auto mt-24 max-w-sm space-y-3 p-4 text-center">
      <p>{state === "working" ? "Verifying…" : state === "ok" ? "Email verified. Thank you!" : "This verification link is invalid or has expired."}</p>
      <Link className="text-brand-600 underline" href="/dashboard">Continue</Link>
    </main>
  );
}
export default function Verify() { return <Suspense><Inner /></Suspense>; }
