"use client";

import { useEffect, useState } from "react";
import { API } from "@/lib/api";

type User = { id: string; email: string; is_active: boolean };
type Cv = { id: string; filename: string; status: string };

export default function AdminDashboard() {
  const [users, setUsers] = useState<User[]>([]); const [cvs, setCvs] = useState<Cv[]>([]); const [error, setError] = useState("");
  const token = typeof window !== "undefined" ? sessionStorage.getItem("admin_access") : null;
  async function request<T>(path: string, options: RequestInit = {}) {
    const headers = new Headers(options.headers); headers.set("Authorization", `Bearer ${token}`); headers.set("X-CSRF-Token", sessionStorage.getItem("admin_csrf") || "");
    const r = await fetch(`${API}${path}`, { ...options, credentials: "include", headers });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Request failed (${r.status})`);
    return r.status === 204 ? undefined as T : await r.json() as T;
  }
  useEffect(() => { if (!token) { location.href = "/admin/login"; return; }
    Promise.all([request<User[]>("/admin/users"), request<Cv[]>("/admin/cvs")]).then(([u, c]) => { setUsers(u); setCvs(c); }).catch(e => setError(e.message)); // eslint-disable-line react-hooks/exhaustive-deps
  }, []);
  async function remove(id: string) { if (!confirm("Delete this CV?")) return; await request(`/admin/cvs/${id}`, { method: "DELETE" }); setCvs(v => v.filter(x => x.id !== id)); }
  return <main className="mx-auto max-w-5xl space-y-4 p-6"><h1 className="text-2xl font-bold">Admin dashboard</h1>{error && <p className="text-red-600">{error}</p>}
    <section className="rounded border bg-white p-4"><h2 className="mb-2 font-semibold">Users</h2><ul>{users.map(u => <li key={u.id} className="border-t py-1">{u.email} · {u.is_active ? "active" : "disabled"}</li>)}</ul></section>
    <section className="rounded border bg-white p-4"><h2 className="mb-2 font-semibold">CVs</h2><ul>{cvs.map(c => <li key={c.id} className="flex justify-between border-t py-1">{c.filename} · {c.status}<button className="text-red-600" onClick={() => remove(c.id)}>Delete</button></li>)}</ul></section>
  </main>;
}
