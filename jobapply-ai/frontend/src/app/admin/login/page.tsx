"use client";

import { useState } from "react";
import { API } from "@/lib/api";

export default function AdminLogin() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const r = await fetch(`${API}/admin/login`, { method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "Unable to sign in");
      sessionStorage.setItem("admin_access", data.access_token);
      sessionStorage.setItem("admin_csrf", data.csrf_token);
      location.href = "/admin";
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to sign in"); setBusy(false); }
  }

  return <main className="mx-auto mt-20 max-w-sm p-4">
    <h1 className="mb-2 text-2xl font-bold">Administrator sign in</h1>
    <p className="mb-4 text-sm text-slate-600">This is separate from the user account login.</p>
    <form onSubmit={submit} className="space-y-3 rounded-lg border bg-white p-4">
      <input className="input" type="email" required autoComplete="username" placeholder="Admin email" value={email} onChange={e => setEmail(e.target.value)} />
      <input className="input" type="password" required autoComplete="current-password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button className="btn-primary w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
    </form>
  </main>;
}
