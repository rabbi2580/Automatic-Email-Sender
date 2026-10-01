"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge, Button, Card, ErrorBox, Spinner, useLoad, useToast } from "@/components/ui";

/* eslint-disable @typescript-eslint/no-explicit-any */
export default function Admin() {
  const { user } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const isAdmin = user?.role === "admin";
  useEffect(() => { if (user && !isAdmin) router.replace("/dashboard"); }, [user, isAdmin, router]);
  const health = useLoad(() => (isAdmin ? api<any>("/admin/health") : Promise.resolve(null)), [isAdmin]);
  const users = useLoad(() => (isAdmin ? api<any[]>("/admin/users") : Promise.resolve([])), [isAdmin]);
  const usage = useLoad(() => (isAdmin ? api<any[]>("/admin/usage") : Promise.resolve([])), [isAdmin]);
  const ai = useLoad(() => (isAdmin ? api<any>("/admin/ai") : Promise.resolve(null)), [isAdmin]);
  const fails = useLoad(() => (isAdmin ? api<any[]>("/admin/delivery-failures") : Promise.resolve([])), [isAdmin]);
  const flags = useLoad(() => (isAdmin ? api<any[]>("/admin/feature-flags") : Promise.resolve([])), [isAdmin]);
  const limits = useLoad(() => (isAdmin ? api<any[]>("/admin/limits") : Promise.resolve([])), [isAdmin]);
  if (!isAdmin) return <Spinner />;

  async function patchUser(id: string, body: any) { try { await api(`/admin/users/${id}`, { method: "PATCH", body }); users.reload(); } catch (e) { toast((e as Error).message, "err"); } }
  async function toggleFlag(f: any) { try { await api("/admin/feature-flags", { method: "PUT", body: { key: f.key, enabled: !f.enabled, description: f.description } }); flags.reload(); } catch (e) { toast((e as Error).message, "err"); } }
  async function setLimit(l: any) {
    const v = prompt(`New limit for ${l.plan}/${l.metric}`, String(l.limit_value));
    if (v === null || isNaN(Number(v))) return;
    try { await api("/admin/limits", { method: "PUT", body: { plan: l.plan, metric: l.metric, limit_value: Number(v) } }); limits.reload(); } catch (e) { toast((e as Error).message, "err"); }
  }
  const h = health.data;
  return (
    <>
      <h1 className="text-xl font-bold">Admin</h1>
      <p className="text-xs text-slate-500">Admin views show aggregates and metadata only. User CVs, job texts and emails are never exposed here.</p>
      <Card title="System health">{health.error ? <ErrorBox error={health.error} onRetry={health.reload} /> : !h ? <Spinner /> :
        <div className="flex flex-wrap gap-2 text-sm"><Badge tone={h.database ? "green" : "red"}>DB {h.database ? "ok" : "down"}</Badge><Badge>tasks: {h.task_mode}</Badge><Badge>AI: {h.ai_provider}</Badge><Badge>users {h.users}</Badge><Badge>jobs 24h {h.jobs_24h}</Badge>
          <Badge tone={h.stuck_jobs ? "red" : "green"}>stuck jobs {h.stuck_jobs}</Badge><Badge tone={h.ai_failure_rate_24h > 0.2 ? "red" : "green"}>AI failures {Math.round(h.ai_failure_rate_24h * 100)}%</Badge><Badge>sends 24h: {JSON.stringify(h.sends_24h)}</Badge></div>}</Card>
      <Card title="Users">
        <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="text-left text-xs text-slate-500"><tr><th>Email</th><th>Plan</th><th>Jobs</th><th>Apps</th><th>Status</th><th /></tr></thead>
          <tbody>{(users.data || []).map((u) => <tr key={u.id} className="border-t"><td className="py-1">{u.email} {u.role === "admin" && <Badge tone="purple">admin</Badge>}</td>
            <td><select className="input !w-24 !py-1" value={u.plan} onChange={(e) => patchUser(u.id, { plan: e.target.value })}>{["free", "pro", "business"].map((p) => <option key={p}>{p}</option>)}</select></td>
            <td>{u.counts.jobs}</td><td>{u.counts.applications}</td><td>{u.is_active ? <Badge tone="green">active</Badge> : <Badge tone="red">suspended</Badge>}{u.flagged_reason && <span className="text-xs text-amber-700"> {u.flagged_reason}</span>}</td>
            <td className="text-right">{u.id !== user?.id && <Button variant="secondary" onClick={() => patchUser(u.id, { is_active: !u.is_active, flagged_reason: u.is_active ? "Suspended by admin" : "" })}>{u.is_active ? "Suspend" : "Reactivate"}</Button>}</td></tr>)}</tbody></table></div>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Usage (all users)"><ul className="space-y-1 text-sm">{(usage.data || []).map((u) => <li key={u.metric} className="flex justify-between"><span>{u.metric}</span><span className="text-slate-600">{u.quantity}{u.est_cost_usd ? ` · $${u.est_cost_usd}` : ""}</span></li>)}</ul></Card>
        <Card title="AI requests (7d)">{ai.data && <><p className="mb-1 text-xs text-slate-500">Provider: {ai.data.configured_provider} · heuristic fallback: {String(ai.data.fallback_to_heuristic)}</p><ul className="space-y-1 text-sm">{ai.data.tasks.map((t: any, i: number) => <li key={i} className="flex justify-between"><span>{t.task} <span className="text-slate-400">({t.provider})</span></span><span className="text-slate-600">{t.success}/{t.requests} ok · {t.cache_hits} cached · {t.avg_latency_ms}ms</span></li>)}</ul></>}</Card>
        <Card title="Feature flags"><ul className="space-y-1 text-sm">{(flags.data || []).map((f) => <li key={f.key} className="flex items-center justify-between"><span>{f.key} <span className="text-xs text-slate-400">{f.description}</span></span><Button variant={f.enabled ? "primary" : "secondary"} onClick={() => toggleFlag(f)}>{f.enabled ? "On" : "Off"}</Button></li>)}{!flags.data?.length && <li className="text-slate-500">No flags defined.</li>}</ul></Card>
        <Card title="Delivery failures (recent)"><ul className="space-y-1 text-xs text-slate-600">{(fails.data || []).slice(0, 15).map((f, i) => <li key={i}>{new Date(f.at).toLocaleString()} · {f.provider} → {f.recipient_domain}: {f.error}</li>)}{!fails.data?.length && <li>None.</li>}</ul></Card>
      </div>
      <Card title="Plan limits"><div className="grid gap-1 text-sm md:grid-cols-3">{(limits.data || []).map((l) => <button key={`${l.plan}${l.metric}`} onClick={() => setLimit(l)} className="flex justify-between rounded border px-2 py-1 text-left hover:bg-slate-50"><span>{l.plan} · {l.metric}</span><b>{l.limit_value}</b></button>)}</div></Card>
    </>
  );
}
