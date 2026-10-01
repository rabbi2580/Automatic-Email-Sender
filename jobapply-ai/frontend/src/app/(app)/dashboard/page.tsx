"use client";
import Link from "next/link";
import { api } from "@/lib/api";
import { Badge, Card, Empty, ErrorBox, Spinner, urgencyTone, useLoad, pretty } from "@/components/ui";

type Analytics = {
  cards: Record<string, number>; classification: Record<string, number>; funnel: Record<string, number>;
  upcoming_deadlines: { job_id: string; title: string; company: string; deadline: string; days_remaining: number | null; urgency: string }[];
  reminders: { application_id: string; title: string; company: string; reminder_at: string }[]; disclaimer: string;
};
const LABELS: [string, string][] = [["jobs_added", "Jobs added"], ["strong_matches", "Strong matches"], ["pending_review", "Pending review"], ["applications_sent", "Applications sent"],
  ["interviews", "Interviews"], ["offers", "Offers"], ["rejected", "Rejected"], ["response_rate", "Response rate %"]];

export default function Dashboard() {
  const { data, error, loading, reload } = useLoad(() => api<Analytics>("/analytics"));
  const usage = useLoad(() => api<{ plan: string; limits: Record<string, { used: number; limit: number; period: string }> }>("/usage"));
  if (loading) return <Spinner />;
  if (error || !data) return <ErrorBox error={error} onRetry={reload} />;
  const empty = !data.cards.jobs_added;
  return (
    <>
      <h1 className="text-xl font-bold">Dashboard</h1>
      {empty && <Empty title="Let’s get started"><ol className="mx-auto max-w-sm list-decimal space-y-1 text-left"><li><Link className="text-brand-600 underline" href="/cvs">Upload your CV</Link></li><li><Link className="text-brand-600 underline" href="/jobs">Add job posts</Link> (paste, URL, PDF, image)</li><li>Review matches and tailored applications</li></ol></Empty>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {LABELS.map(([k, l]) => <Card key={k}><div className="text-2xl font-bold">{data.cards[k] ?? 0}</div><div className="text-xs text-slate-500">{l}</div></Card>)}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Upcoming deadlines (14 days)">
          {data.upcoming_deadlines.length === 0 ? <p className="text-sm text-slate-500">No deadlines in the next two weeks.</p> :
            <ul className="divide-y">{data.upcoming_deadlines.map((d) => (
              <li key={d.job_id} className="flex items-center justify-between py-2 text-sm"><Link href={`/jobs/${d.job_id}`} className="hover:underline">{d.title} <span className="text-slate-500">· {d.company}</span></Link>
                <Badge tone={urgencyTone(d.urgency)}>{d.days_remaining === 0 ? "Today" : `${d.days_remaining}d`}</Badge></li>))}</ul>}
        </Card>
        <Card title="Pipeline">
          {Object.keys(data.funnel).length === 0 ? <p className="text-sm text-slate-500">No applications yet.</p> :
            <div className="flex flex-wrap gap-2">{Object.entries(data.funnel).map(([k, v]) => <Badge key={k} tone="blue">{pretty(k)}: {v}</Badge>)}</div>}
        </Card>
        <Card title="Reminders">
          {data.reminders.length === 0 ? <p className="text-sm text-slate-500">No reminders set.</p> :
            <ul className="space-y-1 text-sm">{data.reminders.map((r) => <li key={r.application_id}><Link className="hover:underline" href={`/applications/${r.application_id}`}>{r.title} · {r.company}</Link> <span className="text-slate-500">{new Date(r.reminder_at).toLocaleDateString()}</span></li>)}</ul>}
        </Card>
        <Card title="Plan usage">
          {usage.data ? <ul className="space-y-1 text-sm"><li className="mb-1"><Badge tone="purple">{usage.data.plan}</Badge></li>{Object.entries(usage.data.limits).map(([k, v]) => <li key={k} className="flex justify-between"><span>{pretty(k)}</span><span className="text-slate-600">{v.used} / {v.limit} <span className="text-xs text-slate-400">{v.period}</span></span></li>)}</ul> : <Spinner />}
        </Card>
      </div>
      <p className="text-xs text-slate-500">{data.disclaimer}</p>
    </>
  );
}
