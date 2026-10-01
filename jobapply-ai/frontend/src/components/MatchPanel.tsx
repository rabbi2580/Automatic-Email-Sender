"use client";
import { Badge, Card, Chips, ScoreBar, classLabel, classTone } from "./ui";

/* eslint-disable @typescript-eslint/no-explicit-any */
const nm = (x: any) => (typeof x === "string" ? x : x?.skill || x?.name || JSON.stringify(x));

export default function MatchPanel({ match }: { match: any }) {
  if (!match) return <p className="text-sm text-slate-500">No match score yet. Upload a CV and make sure this job was analysed.</p>;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3"><div className="text-3xl font-bold">{Math.round(match.score)}%</div><Badge tone={classTone(match.classification)}>{classLabel(match.classification)}</Badge></div>
      <div className="grid gap-3 md:grid-cols-2">
        {Object.entries(match.dimensions || {}).map(([k, d]: [string, any]) => (
          <div key={k}>
            <div className="flex justify-between text-xs"><span className="font-medium">{d.label}</span><span className="text-slate-500">{d.score === null ? "not scored" : `${Math.round(d.score * 100)}% · weight ${Math.round((d.effective_weight || 0) * 100)}%`}</span></div>
            <ScoreBar value={d.score === null ? 0 : d.score * 100} tone={d.score === null ? "bg-slate-300" : d.score >= 0.7 ? "bg-emerald-500" : d.score >= 0.4 ? "bg-amber-500" : "bg-red-500"} />
            <p className="mt-0.5 text-xs text-slate-500">{d.reason}</p>
          </div>))}
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div><div className="label">Strong matches</div><Chips tone="green" items={(match.strong_matches || []).map(nm)} /></div>
        <div><div className="label">Partial</div><Chips tone="amber" items={(match.partial_matches || []).map(nm)} /></div>
        <div><div className="label">Missing / not evidenced</div><Chips tone="red" items={(match.missing || []).map(nm)} /></div>
      </div>
      {match.concerns?.length > 0 && <ul className="list-disc pl-5 text-sm text-amber-800">{match.concerns.map((c: string, i: number) => <li key={i}>{c}</li>)}</ul>}
      <details className="text-sm"><summary className="cursor-pointer text-brand-600">Full explanation</summary><pre className="mt-2 whitespace-pre-wrap rounded bg-slate-50 p-3 text-xs text-slate-700">{match.explanation}</pre></details>
    </div>
  );
}

export function MatchCard({ match }: { match: any }) { return <Card title="Match analysis"><MatchPanel match={match} /></Card>; }
