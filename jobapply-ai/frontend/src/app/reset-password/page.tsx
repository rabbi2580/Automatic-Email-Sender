"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { Button, ErrorBox, Field } from "@/components/ui";

function Inner() {
  const token = useSearchParams().get("token");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<"idle" | "ok" | "bad">("idle");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) { setStatus("bad"); return; }
    setBusy(true); setErr(null);
    try {
      await api("/auth/reset-password", { body: { token, new_password: password }, auth: false });
      setStatus("ok");
    } catch (e2) {
      setErr(e2); setStatus("bad");
    }
    setBusy(false);
  }

  if (!token) {
    return (
      <main className="mx-auto mt-24 max-w-sm space-y-3 p-4 text-center">
        <p>This reset link is missing a token.</p>
        <Link className="text-brand-600 underline" href="/login">Back to sign in</Link>
      </main>
    );
  }

  return (
    <main className="mx-auto mt-16 max-w-sm space-y-4 p-4">
      <h1 className="text-2xl font-bold text-brand-700">Set a new password</h1>
      {status === "ok" ? (
        <div className="space-y-3 rounded-lg border bg-white p-4 text-sm text-slate-700">
          <p>Your password has been reset. You can now sign in with the new password.</p>
          <Link className="text-brand-600 underline" href="/login">Sign in</Link>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-3 rounded-lg border bg-white p-4">
          <Field label="New password" hint="At least 10 characters."><input className="input" type="password" required minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
          <ErrorBox error={err} />
          <Button className="w-full" disabled={busy}>{busy ? "Resetting…" : "Reset password"}</Button>
        </form>
      )}
    </main>
  );
}

export default function ResetPassword() {
  return (
    <Suspense>
      <Inner />
    </Suspense>
  );
}
