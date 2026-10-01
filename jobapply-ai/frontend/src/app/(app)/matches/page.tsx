"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { Badge, Button, Card, Empty, ErrorBox, Spinner, classLabel, classTone, urgencyTone, useLoad, useToast } from "@/components/ui";
import MatchPanel from "@/components/MatchPanel";
import GenerateDialog from "@/components/GenerateDialog";

/* eslint-disable @typescript-eslint/no-explicit-any */
export default function Matches() {
  const toast = useToast();
  const [cls, setCls] = useState("");
  const [min, setMin] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [gen, setGen] = useState<string[]>([]);
  const { data, error, loading, reload } = useLoad(() => api<any[]>(`/matches?min_score=${min}${cls ? `&classification=${cls}` : ""}`), [cls, min]);
  async function recompute() { try { const r = await api<any>("/matches/recompute", { method: "POST" }); toast(`Recomputed ${r.recomputed} match(es).`); reload(); } catch (e) { toast((e as Error).message, "err"); } }
  return (
    <>
      <div className="flex items-center justify-between"><h1 className="text-xl font-bold">Job Matches</h1><Button variant="secondary" onClick={recompute}>Recompute with current weights</Button></div>
      <Card><div className="grid gap-2 md:grid-cols-3">
        <select className="input" value={cls} onChange={(e) => setCls(e.target.value)}><option value="">All</option><option value="strong">Strong</option><option value="potential">Potential</option><option value="weak">Weak</option><option value="not_suitable">Not suitable</option></select>
        <label className="flex items-center gap-2 text-sm">Min score {min}<input type="range" min={0} max={100} value={min} onChange={(e) => setMin(Number(e.target.value))} /></label>
      </div></Card>
      {loading ? <Spinner /> : error ? <ErrorBox error={error} onRetry={reload} /> : !data?.length ? <Empty title="No matches">Add jobs and upload a CV to see scored matches.</Empty> :
        <div className="space-y-2">{data.map((j) => (
          <div key={j.id} className="rounded-lg border bg-white p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div><Link href={`/jobs/${j.id}`} className="font-medium hover:underline">{j.title}</Link><div className="text-sm text-slate-600">{j.company}</div></div>
              <div className="flex items-center gap-2">{j.deadline && <Badge tone={urgencyTone(j.urgency)}>{j.days_remaining}d</Badge>}
                {j.match && <Badge tone={classTone(j.match.classification)}>{Math.round(j.match.score)}% · {classLabel(j.match.classification)}</Badge>}
                <Button variant="ghost" onClick={() => setOpen(open === j.id ? null : j.id)}>{open === j.id ? "Hide" : "Why?"}</Button>
                <Button variant="secondary" onClick={() => setGen([j.id])}>Prepare</Button></div>
            </div>
            {open === j.id && <div className="mt-3 border-t pt-3"><MatchPanel match={j.match} /></div>}
          </div>))}</div>}
      <GenerateDialog open={gen.length > 0} ids={gen} onClose={() => setGen([])} />
    </>
  );
}
