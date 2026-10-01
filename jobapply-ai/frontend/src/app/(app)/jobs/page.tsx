"use client";
import Link from "next/link";
import { useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import GenerateDialog from "@/components/GenerateDialog";
import { Badge, Button, Card, Empty, ErrorBox, Field, Modal, Spinner, classLabel, classTone, pretty, urgencyTone, useLoad, useToast } from "@/components/ui";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Job = any;
type Step = 1 | 2 | 3 | 4 | 5 | 6;
const STEPS = ["Add jobs", "Review parsed", "Fix duplicates", "Match", "Generate", "Review & send"];

export default function Jobs() {
  const toast = useToast();
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("urgency");
  const [cls, setCls] = useState("");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [wizard, setWizard] = useState(false);
  const list = useLoad(() => api<{ total: number; items: Job[] }>(`/jobs?sort=${sort}&limit=200${q ? `&q=${encodeURIComponent(q)}` : ""}${cls ? `&classification=${cls}` : ""}`), [q, sort, cls]);
  const [genOpen, setGenOpen] = useState(false);

  const items = list.data?.items || [];
  const toggle = (id: string) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const selectable = items.filter((j) => j.status !== "failed" && !j.duplicate_of && !j.application);

  async function del(id: string) {
    if (!confirm("Delete this job?")) return;
    try { await api(`/jobs/${id}`, { method: "DELETE" }); list.reload(); } catch (e) { toast((e as Error).message, "err"); }
  }
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2"><h1 className="text-xl font-bold">Find / Add Jobs</h1>
        <div className="flex gap-2"><Button variant="secondary" disabled={sel.size === 0} onClick={() => setGenOpen(true)}>Generate for {sel.size} selected</Button><Button onClick={() => setWizard(true)}>+ Add jobs</Button></div></div>
      <Card>
        <div className="grid gap-2 md:grid-cols-4">
          <input className="input" placeholder="Search title or company" value={q} onChange={(e) => setQ(e.target.value)} />
          <select className="input" value={sort} onChange={(e) => setSort(e.target.value)}><option value="urgency">Sort: deadline (most urgent)</option><option value="score">Sort: match score</option><option value="recent">Sort: recently added</option></select>
          <select className="input" value={cls} onChange={(e) => setCls(e.target.value)}><option value="">All matches</option><option value="strong">Strong</option><option value="potential">Potential</option><option value="weak">Weak</option><option value="not_suitable">Not suitable</option></select>
          <Button variant="ghost" onClick={() => setSel(new Set(selectable.filter((j) => j.match?.classification === "strong" || j.match?.classification === "potential").map((j) => j.id)))}>Select strong + potential</Button>
        </div>
      </Card>
      {list.loading ? <Spinner /> : list.error ? <ErrorBox error={list.error} onRetry={list.reload} /> : items.length === 0 ? <Empty title="No jobs yet">Click “Add jobs” to paste posts, URLs, or upload PDFs / images.</Empty> :
        <div className="space-y-2">{items.map((j) => (
          <div key={j.id} className="flex items-start gap-3 rounded-lg border bg-white p-3">
            <input type="checkbox" aria-label={`Select ${j.title}`} className="mt-1.5" disabled={!selectable.includes(j)} checked={sel.has(j.id)} onChange={() => toggle(j.id)} />
            <div className="min-w-0 flex-1">
              <Link href={`/jobs/${j.id}`} className="font-medium hover:underline">{j.title || "(untitled — needs review)"}</Link>
              <div className="text-sm text-slate-600">{j.company || "Unknown company"} · {j.location || "location not stated"}</div>
              <div className="mt-1 flex flex-wrap gap-1">
                {j.match && <Badge tone={classTone(j.match.classification)}>{Math.round(j.match.score)}% · {classLabel(j.match.classification)}</Badge>}
                {j.deadline && <Badge tone={urgencyTone(j.urgency)}>{j.days_remaining != null && j.days_remaining < 0 ? "Deadline passed" : `${j.days_remaining}d left`} · {j.deadline}</Badge>}
                {j.status !== "completed" && <Badge tone={j.status === "failed" ? "red" : "amber"}>{pretty(j.status)}</Badge>}
                {j.duplicate_of && <Badge tone="amber">Possible duplicate</Badge>}
                {j.application && <Badge tone="purple">Application: {pretty(j.application.status)}</Badge>}
                {!j.application_email && j.application_url && <Badge>Apply via link</Badge>}
              </div>
              {j.status_reason && <p className="mt-1 text-xs text-amber-700">{j.status_reason}</p>}
            </div>
            <Button variant="ghost" onClick={() => del(j.id)}>Delete</Button>
          </div>))}</div>}
      <Wizard open={wizard} onClose={() => { setWizard(false); list.reload(); }} />
      <GenerateDialog open={genOpen} ids={[...sel]} onClose={() => setGenOpen(false)} />
    </>
  );
}

/* ---------- 6-step intake wizard ---------- */
function Wizard({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const [step, setStep] = useState<Step>(1);
  const [text, setText] = useState("");
  const [urls, setUrls] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const files = useRef<HTMLInputElement>(null);
  const [apps, setApps] = useState<any[]>([]);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [skipped, setSkipped] = useState<any[]>([]);

  const reset = () => { setStep(1); setText(""); setUrls(""); setJobs([]); setSummary(null); setApps([]); setSel(new Set()); setErr(null); setSkipped([]); };
  const close = () => { onClose(); reset(); };

  async function submit() {
    setBusy(true); setErr(null);
    try {
      const items: any[] = [];
      if (text.trim()) items.push({ kind: "text", text, split: true });
      urls.split("\n").map((u) => u.trim()).filter(Boolean).forEach((u) => items.push({ kind: "url", url: u }));
      let all: Job[] = [];
      if (items.length) { const r = await api<any>("/jobs/bulk", { body: { items } }); all = all.concat(r.jobs); }
      const f = files.current?.files;
      if (f?.length) { const fd = new FormData(); Array.from(f).forEach((x) => fd.append("files", x)); const r = await api<any>("/jobs/upload", { form: fd }); all = all.concat(r.jobs); }
      if (!all.length) { setErr(new Error("Paste at least one job post, URL, or choose a file.")); setBusy(false); return; }
      setJobs(all); setStep(2);
    } catch (e) { setErr(e); }
    setBusy(false);
  }
  async function retry(id: string) {
    try { const j = await api<Job>(`/jobs/${id}/retry`, { method: "POST" }); setJobs((x) => x.map((y) => (y.id === id ? j : y))); } catch (e) { toast((e as Error).message, "err"); }
  }
  async function notDup(id: string) {
    try { const j = await api<Job>(`/jobs/${id}/not-duplicate`, { method: "POST" }); setJobs((x) => x.map((y) => (y.id === id ? j : y))); } catch (e) { toast((e as Error).message, "err"); }
  }
  async function removeJob(id: string) {
    try { await api(`/jobs/${id}`, { method: "DELETE" }); setJobs((x) => x.filter((y) => y.id !== id)); } catch (e) { toast((e as Error).message, "err"); }
  }
  async function match() {
    setBusy(true); setErr(null);
    try {
      const ids = jobs.filter((j) => j.status !== "failed" && !j.duplicate_of).map((j) => j.id);
      if (!ids.length) throw new Error("No analysable jobs to match.");
      const r = await api<any>("/jobs/analyze", { body: { job_ids: ids } });
      setJobs((x) => x.map((o) => r.jobs.find((n: Job) => n.id === o.id) || o)); setSummary(r.summary); setStep(4);
      setSel(new Set(r.jobs.filter((j: Job) => ["strong", "potential"].includes(j.match?.classification)).map((j: Job) => j.id)));
    } catch (e) { setErr(e); }
    setBusy(false);
  }
  async function generate() {
    setBusy(true); setErr(null);
    try {
      const r = await api<any>("/applications/generate", { body: { job_ids: [...sel] } });
      setApps(r.applications); setSkipped(r.skipped); setStep(6);
    } catch (e) { setErr(e); }
    setBusy(false);
  }
  const dups = useMemo(() => jobs.filter((j) => j.duplicate_of), [jobs]);
  const failed = useMemo(() => jobs.filter((j) => j.status === "failed" || j.status === "requires_review"), [jobs]);

  return (
    <Modal open={open} onClose={close} title="Add jobs" wide>
      <ol className="mb-4 flex flex-wrap gap-2 text-xs">{STEPS.map((s, i) => <li key={s} className={`rounded-full px-2 py-1 ${step === i + 1 ? "bg-brand-600 text-white" : step > i + 1 ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-500"}`}>{i + 1}. {s}</li>)}</ol>
      <div className="space-y-3">
        {step === 1 && <>
          <Field label="Paste job posts (several at once is fine — separate them with a blank line and a title)"><textarea className="input" rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste job text, or an email that contains a job post…" /></Field>
          <Field label="Job URLs (one per line)" hint="Login-walled sites (LinkedIn, Facebook) can’t be fetched — paste the text instead."><textarea className="input" rows={3} value={urls} onChange={(e) => setUrls(e.target.value)} /></Field>
          <Field label="Files: PDF, DOCX, or screenshot images"><input ref={files} type="file" multiple accept=".pdf,.docx,.png,.jpg,.jpeg,.webp" className="text-sm" /></Field>
          <ErrorBox error={err} />
          <div className="text-right"><Button onClick={submit} disabled={busy}>{busy ? "Analysing…" : "Parse jobs"}</Button></div></>}
        {step === 2 && <>
          <p className="text-sm text-slate-600">{jobs.length} job(s) found. Check what was extracted.</p>
          <div className="max-h-80 space-y-2 overflow-y-auto">{jobs.map((j) => (
            <div key={j.id} className="rounded border p-2 text-sm">
              <div className="flex items-center justify-between gap-2"><div><b>{j.title || "(no title)"}</b> · {j.company || "unknown company"} <span className="text-slate-500">{j.deadline ? `· deadline ${j.deadline}` : "· no deadline found"}</span></div>
                <Badge tone={j.status === "failed" ? "red" : j.status === "requires_review" ? "amber" : "green"}>{pretty(j.status)}</Badge></div>
              {j.status_reason && <p className="text-xs text-amber-700">{j.status_reason}</p>}
              {(j.warnings || []).map((w: string, i: number) => <p key={i} className="text-xs text-amber-700">⚠ {w}</p>)}
              <div className="mt-1 flex gap-2"><Link className="text-xs text-brand-600 underline" target="_blank" href={`/jobs/${j.id}`}>Edit details</Link>
                {(j.status === "failed" || j.status === "requires_review") && <button className="text-xs text-brand-600 underline" onClick={() => retry(j.id)}>Retry</button>}
                <button className="text-xs text-red-600 underline" onClick={() => removeJob(j.id)}>Remove</button></div>
            </div>))}</div>
          {failed.length > 0 && <p className="text-xs text-amber-700">{failed.length} job(s) need attention. Open “Edit details” to enter them manually, or retry.</p>}
          <div className="flex justify-between"><Button variant="secondary" onClick={() => setStep(1)}>Back</Button><Button onClick={() => setStep(3)}>Next</Button></div></>}
        {step === 3 && <>
          {dups.length === 0 ? <p className="text-sm text-slate-600">No duplicates detected.</p> :
            <div className="space-y-2">{dups.map((j) => (
              <div key={j.id} className="rounded border border-amber-200 bg-amber-50 p-2 text-sm"><b>{j.title}</b> · {j.company}<p className="text-xs">{j.duplicate_message} {(j.duplicate_reasons || []).join(", ")}</p>
                <div className="mt-1 flex gap-2"><Button variant="secondary" onClick={() => notDup(j.id)}>Not a duplicate</Button><Button variant="ghost" onClick={() => removeJob(j.id)}>Remove it</Button></div></div>))}</div>}
          <ErrorBox error={err} />
          <div className="flex justify-between"><Button variant="secondary" onClick={() => setStep(2)}>Back</Button><Button onClick={match} disabled={busy}>{busy ? "Matching…" : "Compute matches"}</Button></div></>}
        {step === 4 && <>
          {summary && <div className="flex flex-wrap gap-2 text-sm">{Object.entries(summary).map(([k, v]) => <Badge key={k} tone="blue">{pretty(k)}: {String(v)}</Badge>)}</div>}
          <p className="text-sm text-slate-600">Choose which jobs to prepare applications for. Strong and potential matches are pre-selected.</p>
          <div className="max-h-72 space-y-1 overflow-y-auto">{jobs.filter((j) => j.match).sort((a, b) => b.match.score - a.match.score).map((j) => (
            <label key={j.id} className="flex items-center gap-2 rounded border p-2 text-sm"><input type="checkbox" checked={sel.has(j.id)} onChange={() => setSel((s) => { const n = new Set(s); n.has(j.id) ? n.delete(j.id) : n.add(j.id); return n; })} />
              <span className="flex-1">{j.title} · {j.company}</span><Badge tone={classTone(j.match.classification)}>{Math.round(j.match.score)}% {classLabel(j.match.classification)}</Badge></label>))}</div>
          <div className="flex justify-between"><Button variant="secondary" onClick={() => setStep(3)}>Back</Button><Button onClick={() => setStep(5)} disabled={sel.size === 0}>Next ({sel.size})</Button></div></>}
        {step === 5 && <>
          <p className="text-sm">Generate a tailored CV, cover letter and email for <b>{sel.size}</b> job(s)? Each is built only from your profile and then checked automatically. Nothing is sent.</p>
          <ErrorBox error={err} />
          <div className="flex justify-between"><Button variant="secondary" onClick={() => setStep(4)}>Back</Button><Button onClick={generate} disabled={busy}>{busy ? "Generating…" : "Generate applications"}</Button></div></>}
        {step === 6 && <>
          <p className="text-sm text-slate-600">{apps.length} application(s) prepared. Review each one, then approve and send from the Applications page.</p>
          {skipped.map((s, i) => <p key={i} className="text-xs text-amber-700">Skipped: {s.reason}</p>)}
          <div className="flex justify-end gap-2"><Button variant="secondary" onClick={close}>Close</Button><Link href="/applications"><Button>Go to review queue</Button></Link></div></>}
      </div>
    </Modal>
  );
}

