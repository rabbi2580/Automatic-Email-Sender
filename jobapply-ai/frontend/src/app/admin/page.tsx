"use client";

import { useEffect, useState } from "react";
import { API } from "@/lib/api";

type User = { id: string; email: string; is_active: boolean };
type Cv = { id: string; filename: string; status: string };
type Analytics = { users: { total: number; last_24h: number; last_7d: number }; cvs: { total: number; completed: number; needs_review: number; failed: number; queued: number; processing: number }; parse_success_rate: number };
type ParseError = { id: string; filename: string; reason: string | null; updated_at: string };

export default function AdminDashboard() {
  const [users, setUsers] = useState<User[]>([]); const [cvs, setCvs] = useState<Cv[]>([]); const [stats, setStats] = useState<Analytics | null>(null); const [parseErrors, setParseErrors] = useState<ParseError[]>([]); const [error, setError] = useState("");
  const token = typeof window !== "undefined" ? sessionStorage.getItem("admin_access") : null;
  async function request<T>(path: string, options: RequestInit = {}) {
    const headers = new Headers(options.headers); headers.set("Authorization", `Bearer ${token}`); headers.set("X-CSRF-Token", sessionStorage.getItem("admin_csrf") || "");
    const r = await fetch(`${API}${path}`, { ...options, credentials: "include", headers });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Request failed (${r.status})`);
    return r.status === 204 ? undefined as T : await r.json() as T;
  }
  useEffect(() => { if (!token) { location.href = "/admin/login"; return; }
    Promise.all([request<User[]>("/admin/users"), request<Cv[]>("/admin/cvs"), request<Analytics>("/admin/analytics"), request<ParseError[]>("/admin/parse-errors")]).then(([u, c, a, p]) => { setUsers(u); setCvs(c); setStats(a); setParseErrors(p); }).catch(e => setError(e.message)); // eslint-disable-line react-hooks/exhaustive-deps
  }, []);
  async function remove(id: string) { if (!confirm("Delete this CV?")) return; await request(`/admin/cvs/${id}`, { method: "DELETE" }); setCvs(v => v.filter(x => x.id !== id)); }
  async function retry(id: string) { await request(`/admin/cvs/${id}/retry`, { method: "POST" }); setParseErrors(v => v.filter(x => x.id !== id)); }
  async function exportUsers() { const r = await fetch(`${API}/admin/users.csv`, { headers: { Authorization: `Bearer ${token}` } }); if (!r.ok) { setError("Could not export users."); return; } const a = document.createElement("a"); a.href = URL.createObjectURL(await r.blob()); a.download = "users.csv"; a.click(); URL.revokeObjectURL(a.href); }
  return <main className="mx-auto max-w-5xl space-y-4 p-6"><h1 className="text-2xl font-bold">Admin dashboard</h1>{error && <p className="text-red-600">{error}</p>}
    {stats && <section className="grid gap-3 sm:grid-cols-4">{[["Users", stats.users.total], ["New · 7d", stats.users.last_7d], ["CVs", stats.cvs.total], ["Parse success", `${stats.parse_success_rate}%`]].map(([label, value]) => <div key={String(label)} className="rounded-2xl border bg-white p-4 shadow-sm"><p className="text-xs font-bold uppercase tracking-wide text-slate-500">{label}</p><p className="mt-2 text-2xl font-extrabold text-indigo-700">{value}</p></div>)}</section>}
    <section className="rounded border bg-white p-4"><div className="mb-2 flex items-center justify-between"><h2 className="font-semibold">Users</h2><button className="text-sm font-bold text-indigo-600" onClick={exportUsers}>Export CSV</button></div><ul>{users.map(u => <li key={u.id} className="border-t py-1">{u.email} · {u.is_active ? "active" : "disabled"}</li>)}</ul></section>
    <section className="rounded border bg-white p-4"><h2 className="mb-2 font-semibold">CVs</h2><ul>{cvs.map(c => <li key={c.id} className="flex justify-between border-t py-1">{c.filename} · {c.status}<button className="text-red-600" onClick={() => remove(c.id)}>Delete</button></li>)}</ul></section>
    <section className="rounded border bg-white p-4"><h2 className="mb-2 font-semibold">Parse errors</h2>{parseErrors.length ? <ul>{parseErrors.map(p => <li key={p.id} className="flex flex-wrap justify-between gap-2 border-t py-2 text-sm"><span><b>{p.filename}</b><br /><span className="text-red-700">{p.reason || "Unknown parsing error"}</span></span><button className="font-bold text-indigo-600" onClick={() => retry(p.id)}>Retry</button></li>)}</ul> : <p className="text-sm text-slate-500">No failed parses.</p>}</section>
  </main>;
}
