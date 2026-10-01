"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import SendDialog from "@/components/SendDialog";
import { Badge, Button, Card, Empty, ErrorBox, Spinner, classLabel, classTone, pretty, statusTone, urgencyTone, useLoad, useToast } from "@/components/ui";

/* eslint-disable @typescript-eslint/no-explicit-any */
const STAGES = ["", "awaiting_review", "approved", "sent", "application_confirmed", "interview", "offer", "rejected", "withdrawn"];

export default function Applications() {
  const toast = useToast();
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("updated");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const { data, error, loading, reload } = useLoad(() => api<{ total: number; items: any[] }>(`/applications?sort=${sort}${status ? `&status=${status}` : ""}`), [status, sort]);
  const [sendIds, setSendIds] = useState<string[]>([]);
  const items = data?.items || [];

  const toggle = (id: string) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  async function bulkApprove() {
    try {
      const r = await api<any>("/applications/approve-bulk", { body: { application_ids: [...sel] } });
      const bad = (r.results || []).filter((x: any) => !x.ok);
      toast(bad.length ? `Approved ${(r.results || []).length - bad.length}; ${bad.length} need fixes (open them to see why).` : "Approved.", bad.length ? "err" : "ok");
      reload();
    } catch (e) { toast((e as Error).message, "err"); }
  }
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2"><h1 className="text-xl font-bold">Applications</h1>
        <div className="flex gap-2"><Button variant="secondary" disabled={!sel.size} onClick={bulkApprove}>Approve {sel.size} selected</Button><Button disabled={!sel.size} onClick={() => setSendIds([...sel])}>Review &amp; send {sel.size}</Button></div></div>
      <Card><div className="grid gap-2 md:grid-cols-3">
        <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>{STAGES.map((s) => <option key={s} value={s}>{s ? pretty(s) : "All statuses"}</option>)}</select>
        <select className="input" value={sort} onChange={(e) => setSort(e.target.value)}><option value="updated">Recently updated</option><option value="urgency">Deadline</option><option value="score">Match score</option></select>
      </div></Card>
      {loading ? <Spinner /> : error ? <ErrorBox error={error} onRetry={reload} /> : items.length === 0 ? <Empty title="No applications">Pick jobs on the <Link className="underline" href="/jobs">Jobs</Link> page and generate drafts.</Empty> :
        <div className="overflow-x-auto rounded-lg border bg-white"><table className="w-full text-sm"><thead className="bg-slate-50 text-left text-xs text-slate-500"><tr><th className="p-2" /><th className="p-2">Job</th><th className="p-2">Match</th><th className="p-2">Deadline</th><th className="p-2">Status</th><th className="p-2">Checks</th></tr></thead>
          <tbody>{items.map((a) => (
            <tr key={a.id} className="border-t">
              <td className="p-2"><input type="checkbox" aria-label="select" checked={sel.has(a.id)} onChange={() => toggle(a.id)} /></td>
              <td className="p-2"><Link className="font-medium hover:underline" href={`/applications/${a.id}`}>{a.title}</Link><div className="text-xs text-slate-500">{a.company}{a.sent_at ? ` · sent ${new Date(a.sent_at).toLocaleDateString()}` : ""}</div></td>
              <td className="p-2">{a.score != null && <Badge tone={classTone(a.classification)}>{Math.round(a.score)}% {classLabel(a.classification)}</Badge>}</td>
              <td className="p-2">{a.deadline ? <Badge tone={urgencyTone(a.urgency)}>{a.days_remaining}d</Badge> : "—"}</td>
              <td className="p-2"><Badge tone={statusTone(a.status)}>{pretty(a.status)}</Badge>{a.generation_status !== "completed" && <div className="text-xs text-amber-700">{pretty(a.generation_status)} {a.generation_reason}</div>}</td>
              <td className="p-2">{a.qc_passed === true ? <Badge tone="green">Passed</Badge> : a.qc_passed === false ? <Badge tone="red">Blocked</Badge> : "—"}</td>
            </tr>))}</tbody></table></div>}

      <SendDialog ids={sendIds} onClose={() => setSendIds([])} onDone={() => { reload(); setSel(new Set()); }} />
    </>
  );
}
