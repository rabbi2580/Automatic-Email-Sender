"use client";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Badge, Button, Card, Chips, ErrorBox, Field, Spinner, pretty, urgencyTone, useLoad, useToast } from "@/components/ui";
import MatchPanel from "@/components/MatchPanel";
import GenerateDialog from "@/components/GenerateDialog";

/* eslint-disable @typescript-eslint/no-explicit-any */
const csv = (a?: string[]) => (a || []).join(", ");
const unCsv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

export default function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const { data, error, loading, reload } = useLoad(() => api<any>(`/jobs/${id}`), [id]);
  const [f, setF] = useState<any>(null);
  const [gen, setGen] = useState(false);
  const [ats, setAts] = useState<any>(null);
  useEffect(() => { if (data) setF({ company_name: data.company, job_title: data.title, location: data.location, application_email: data.application_email || "", application_url: data.application_url || "", deadline: data.deadline || "", salary: data.salary || "", required_skills: data.required_skills, preferred_skills: data.preferred_skills, tech_stack: data.tech_stack }); }, [data]);
  if (loading || !f) return error ? <ErrorBox error={error} onRetry={reload} /> : <Spinner />;
  async function save() {
    try {
      const body = { ...f, deadline: f.deadline || null, application_email: f.application_email || null, application_url: f.application_url || null };
      await api(`/jobs/${id}`, { method: "PATCH", body }); toast("Job updated and re-matched."); reload();
    } catch (e) { toast((e as Error).message, "err"); }
  }
  async function retry() { try { await api(`/jobs/${id}/retry`, { method: "POST" }); reload(); } catch (e) { toast((e as Error).message, "err"); } }
  async function score() { try { setAts(await api(`/jobs/${id}/ats-score`, { method: "POST" })); toast("ATS score updated."); } catch (e) { toast((e as Error).message, "err"); } }
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h1 className="text-xl font-bold">{data.title || "Job details"}</h1><p className="text-sm text-slate-600">{data.company}</p></div>
        <div className="flex gap-2">{data.deadline && <Badge tone={urgencyTone(data.urgency)}>{data.days_remaining}d left</Badge>}<Badge>{pretty(data.status)}</Badge>
          {data.application ? <Button onClick={() => router.push(`/applications/${data.application.id}`)}>Open application</Button> : <Button onClick={() => setGen(true)} disabled={data.status === "failed"}>Prepare application</Button>}</div>
      </div>
      {data.status_reason && <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm">{data.status_reason} <button className="underline" onClick={retry}>Retry</button></div>}
      {data.duplicate_of && <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm">{data.duplicate_message}</div>}
      <Card title="Match analysis"><MatchPanel match={data.match} /></Card>
      <Card title="ATS readiness" actions={<Button variant="secondary" onClick={score}>Score my CV</Button>}>{ats ? <div className="space-y-2 text-sm"><div className="text-2xl font-bold text-brand-700">{ats.score}%</div><p>Matched keywords: {ats.matched_keywords?.join(", ") || "none"}</p><p className="text-amber-700">Suggestions: {ats.tips?.join(" ") || "No obvious gaps."}</p></div> : <p className="text-sm text-slate-500">Compare your profile against this job’s keywords and section completeness.</p>}</Card>
      <Card title="Details (editable — corrections re-run the match)" actions={<Button onClick={save}>Save</Button>}>
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Company"><input className="input" value={f.company_name || ""} onChange={(e) => setF({ ...f, company_name: e.target.value })} /></Field>
          <Field label="Title"><input className="input" value={f.job_title || ""} onChange={(e) => setF({ ...f, job_title: e.target.value })} /></Field>
          <Field label="Location"><input className="input" value={f.location || ""} onChange={(e) => setF({ ...f, location: e.target.value })} /></Field>
          <Field label="Salary (as written)"><input className="input" value={f.salary} onChange={(e) => setF({ ...f, salary: e.target.value })} /></Field>
          <Field label="Application email"><input className="input" type="email" value={f.application_email} onChange={(e) => setF({ ...f, application_email: e.target.value })} /></Field>
          <Field label="Application link"><input className="input" value={f.application_url} onChange={(e) => setF({ ...f, application_url: e.target.value })} /></Field>
          <Field label="Deadline"><input className="input" type="date" value={f.deadline} onChange={(e) => setF({ ...f, deadline: e.target.value })} /></Field>
          <Field label="Required skills (comma separated)"><input className="input" value={csv(f.required_skills)} onChange={(e) => setF({ ...f, required_skills: unCsv(e.target.value) })} /></Field>
          <Field label="Preferred skills"><input className="input" value={csv(f.preferred_skills)} onChange={(e) => setF({ ...f, preferred_skills: unCsv(e.target.value) })} /></Field>
          <Field label="Tech stack"><input className="input" value={csv(f.tech_stack)} onChange={(e) => setF({ ...f, tech_stack: unCsv(e.target.value) })} /></Field>
        </div>
      </Card>
      <Card title="Responsibilities"><ul className="list-disc space-y-1 pl-5 text-sm">{(data.responsibilities || []).map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>{!data.responsibilities?.length && <p className="text-sm text-slate-500">None extracted.</p>}</Card>
      <Card title="Skills"><div className="space-y-2"><div><div className="label">Required</div><Chips items={data.required_skills} /></div><div><div className="label">Preferred</div><Chips items={data.preferred_skills} /></div></div></Card>
      <GenerateDialog open={gen} ids={[id]} onClose={() => setGen(false)} />
    </>
  );
}
