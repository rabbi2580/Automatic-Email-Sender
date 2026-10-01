"use client";
import Link from "next/link";
import { useState } from "react";
import { api, tokens } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button, ErrorBox, Field } from "@/components/ui";

export default function Login() {
  const { reload } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      const t = await api<{ access_token: string; refresh_token: string }>("/auth/login", { body: { email, password }, auth: false });
      tokens.set(t.access_token, t.refresh_token);
      await reload();
      location.href = "/dashboard";
    } catch (e2) { setErr(e2); setBusy(false); }
  }
  async function google() {
    try { const r = await api<{ authorization_url: string }>("/auth/google/login", { auth: false }); location.href = r.authorization_url; } catch (e2) { setErr(e2); }
  }
  return (
    <main className="mx-auto mt-20 max-w-sm space-y-4 p-4">
      <h1 className="text-2xl font-bold text-brand-700">JobApply AI</h1>
      <p className="text-sm text-slate-600">Sign in to manage your applications.</p>
      <form onSubmit={submit} className="space-y-3 rounded-lg border bg-white p-4">
        <Field label="Email"><input className="input" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Field label="Password"><input className="input" type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
        <div className="text-right text-sm"><Link className="text-brand-600 underline" href="/forgot-password">Forgot password?</Link></div>
        <ErrorBox error={err} />
        <Button className="w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
        <Button type="button" variant="secondary" className="w-full" onClick={google}>Continue with Google</Button>
      </form>
      <p className="text-sm text-slate-600">New here? <Link className="text-brand-600 underline" href="/register">Create an account</Link></p>
    </main>
  );
}
