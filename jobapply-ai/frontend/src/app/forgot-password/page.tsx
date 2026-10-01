"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { Button, ErrorBox, Field } from "@/components/ui";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [devToken, setDevToken] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = await api<{ sent: boolean; dev_reset_token?: string }>('/auth/forgot-password', { body: { email }, auth: false });
      setSent(r.sent);
      setDevToken(r.dev_reset_token || "");
    } catch (e2) {
      setErr(e2);
      setBusy(false);
    }
    setBusy(false);
  }

  return (
    <main className="mx-auto mt-16 max-w-sm space-y-4 p-4">
      <h1 className="text-2xl font-bold text-brand-700">Reset your password</h1>
      {sent ? (
        <div className="space-y-3 rounded-lg border bg-white p-4 text-sm text-slate-700">
          <p>If an account exists for that email, a reset link has been sent.</p>
          {devToken && <p className="rounded-md bg-amber-50 p-2 text-xs text-amber-900">Development token: <span className="font-mono break-all">{devToken}</span></p>}
          <Link className="text-brand-600 underline" href="/login">Back to sign in</Link>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-3 rounded-lg border bg-white p-4">
          <Field label="Email"><input className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <ErrorBox error={err} />
          <Button className="w-full" disabled={busy}>{busy ? "Sending…" : "Send reset link"}</Button>
        </form>
      )}
    </main>
  );
}
