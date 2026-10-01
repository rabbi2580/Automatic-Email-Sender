"use client";
import Link from "next/link";
import { useState } from "react";
import { api, tokens } from "@/lib/api";
import { Button, ErrorBox, Field } from "@/components/ui";

export default function Register() {
  const [f, setF] = useState({ full_name: "", email: "", password: "" });
  const [terms, setTerms] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      await api("/auth/register", { body: { ...f, accept_terms: terms }, auth: false });
      const t = await api<{ access_token: string; refresh_token: string }>("/auth/login", { body: { email: f.email, password: f.password }, auth: false });
      tokens.set(t.access_token, t.refresh_token);
      location.href = "/profile";
    } catch (e2) { setErr(e2); setBusy(false); }
  }
  return (
    <main className="mx-auto mt-16 max-w-sm space-y-4 p-4">
      <h1 className="text-2xl font-bold text-brand-700">Create your account</h1>
      <form onSubmit={submit} className="space-y-3 rounded-lg border bg-white p-4">
        <Field label="Full name"><input className="input" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field>
        <Field label="Email"><input className="input" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Password" hint="At least 10 characters."><input className="input" type="password" required minLength={10} autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        <label className="flex items-start gap-2 text-xs text-slate-600"><input type="checkbox" checked={terms} onChange={(e) => setTerms(e.target.checked)} className="mt-0.5" />
          <span>I accept the Terms of Service and Privacy Policy, and understand that AI drafts must be reviewed by me before anything is sent.</span></label>
        <ErrorBox error={err} />
        <Button className="w-full" disabled={busy || !terms}>{busy ? "Creating…" : "Create account"}</Button>
      </form>
      <p className="text-sm text-slate-600">Already registered? <Link className="text-brand-600 underline" href="/login">Sign in</Link></p>
    </main>
  );
}
