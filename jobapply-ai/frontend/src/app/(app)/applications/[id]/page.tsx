"use client";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, openSigned } from "@/lib/api";
import { Badge, Button, Card, Chips, ErrorBox, Field, Modal, Spinner, pretty, statusTone, useLoad, useToast } from "@/components/ui";
import MatchPanel from "@/components/MatchPanel";
import SendDialog from "@/components/SendDialog";

/* eslint-disable @typescript-eslint/no-explicit-any */
const TRACK = ["application_confirmed", "interview", "offer", "rejected", "withdrawn", "saved"];

export default function ApplicationDetail() {
  const { id } = useParams<{ id: string }>();
  const toast = useToast();
  const { data: a, error, loading, reload } = useLoad(() => api<any>(`/applications/${id}`), [id]);
  const [tab, setTab] = useState<"overview" | "cv" | "letter" | "email" | "track">("overview");
  const [letter, setLetter] = useState("");
  const [em, setEm] = useState<any>(null);
  const [notes, setNotes] = useState("");
  const [remind, setRemind] = useState("");
  const [sendIds, setSendIds] = useState<string[]>([]);
  const [regen, setRegen] = useState(false);
  const [ro, setRo] = useState<any>({ tone: "professional", language: "en", template: "classic", pages: 1 });
  const accounts = useLoad(() => api<any[]>("/integrations/email"));
  const [busy, setBusy] = useState(false);

  // Poll while the draft is still being generated (celery mode).
  useEffect(() => {
    if (!a || !["queued", "processing"].includes(a.generation_status)) return;
    const t = setTimeout(reload, 2000);
    return () => clearTimeout(t);
  }, [a, reload]);
  useEffect(() => {
    if (!a) return;
    setLetter(a.cover_letter?.body || ""); setEm(a.email ? { to_address: a.email.to_address, subject: a.email.subject, body: a.email.body, email_account_id: a.email.email_account_id || "" } : null);
    setNotes(a.notes || ""); setRemind(a.reminder_at ? a.reminder_at.slice(0, 10) : "");
  }, [a]);
  if (loading && !a) return <Spinner />;
  if (error || !a) return <ErrorBox error={error} onRetry={reload} />;

  const wrap = async (fn: () => Promise<unknown>, ok: string) => { setBusy(true); try { await fn(); toast(ok); await reload(); } catch (e) { toast((e as Error).message, "err"); } setBusy(false); };
  const approve = () => wrap(() => api(`/applications/${id}/approve`, { method: "POST" }), "Approved. Nothing has been sent yet.");
  const reject = () => confirm("Reject this draft? It will not be sent.") && wrap(() => api(`/applications/${id}/reject`, { method: "POST" }), "Draft rejected.");
  const qc = () => wrap(() => api(`/applications/${id}/qc`, { method: "POST" }), "Checks re-run.");
  const saveLetter = () => wrap(() => api(`/applications/${id}/cover-letter`, { method: "PATCH", body: { body: letter } }), "Cover letter saved. Approval (if any) was reset.");
  const saveEmail = () => wrap(() => api(`/applications/${id}/email`, { method: "PATCH", body: { to_address: em.to_address, subject: em.subject, body: em.body, ...(em.email_account_id ? { email_account_id: em.email_account_id } : {}) } }), "Email saved. Approval (if any) was reset.");
  const saveTrack = () => wrap(() => api(`/applications/${id}`, { method: "PATCH", body: { notes, reminder_at: remind ? new Date(remind).toISOString() : null } }), "Saved.");
  const setStatus = (s: string) => wrap(() => api(`/applications/${id}`, { method: "PATCH", body: { status: s } }), `Moved to ${pretty(s)}.`);
  const manual = () => wrap(() => api(`/applications/${id}/mark-applied`, { method: "POST" }), "Marked as applied.");
  const regenerate = async () => { setRegen(false); await wrap(() => api(`/applications/${id}/regenerate`, { body: ro }), "Regenerated."); };

  const qcr = a.qc;
  const canApprove = a.status === "awaiting_review";
  const canSend = a.status === "approved" && a.has_email;
  const cv = a.cv?.content;
  const pending = ["queued", "processing"].includes(a.generation_status);
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div><h1 className="text-xl font-bold">{a.title}</h1><p className="text-sm text-slate-600">{a.company}</p>
          <div className="mt-1 flex gap-2"><Badge tone={statusTone(a.status)}>{pretty(a.status)}</Badge>{a.qc_passed === true && <Badge tone="green">Checks passed</Badge>}{a.qc_passed === false && <Badge tone="red">Blocked by checks</Badge>}{pending && <Badge tone="amber">Generating…</Badge>}</div></div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" disabled={busy || pending} onClick={() => setRegen(true)}>Regenerate</Button>
          <Button variant="secondary" disabled={busy} onClick={qc}>Re-run checks</Button>
          {canApprove && <><Button variant="ghost" disabled={busy} onClick={reject}>Reject</Button><Button disabled={busy || a.qc_passed !== true} onClick={approve}>Approve</Button></>}
          {canSend && <Button onClick={() => setSendIds([a.id])}>Review &amp; send…</Button>}
          {!a.has_email && a.has_url && a.status !== "sent" && <><Button variant="secondary" onClick={() => window.open(a.job.application_url, "_blank", "noopener")}>Open application link</Button><Button variant="secondary" onClick={manual}>I applied manually</Button></>}
        </div>
      </div>
      {a.generation_status === "failed" && <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm">Generation failed: {a.generation_reason}</div>}
      <div role="tablist" className="flex gap-1 border-b">{(["overview", "cv", "letter", "email", "track"] as const).map((t) => <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={`px-3 py-2 text-sm ${tab === t ? "border-b-2 border-brand-600 font-semibold text-brand-700" : "text-slate-600"}`}>{{ overview: "Overview & checks", cv: "Tailored CV", letter: "Cover letter", email: "Email", track: "Tracking" }[t]}</button>)}</div>

      {tab === "overview" && <>
        <Card title="Quality checks">
          {!qcr ? <p className="text-sm text-slate-500">Not run yet.</p> : <div className="space-y-2">
            <p className={`text-sm font-medium ${qcr.passed ? "text-emerald-700" : "text-red-700"}`}>{qcr.summary}</p>
            <ul className="space-y-1 text-sm">{qcr.checks.map((c: any) => <li key={c.id} className="flex gap-2"><span>{c.ok ? "✅" : c.severity === "block" ? "⛔" : "⚠️"}</span><span className={c.ok ? "text-slate-500" : ""}>{c.ok ? `${pretty(c.id.replace(/\./g, " "))} — OK` : c.message}</span></li>)}</ul></div>}
        </Card>
        <Card title="Match"><MatchPanel match={a.match} /></Card>
        <Card title="Documents">
          {a.documents.length === 0 ? <p className="text-sm text-slate-500">No documents yet.</p> : <ul className="divide-y text-sm">{a.documents.map((d: any) => <li key={d.id} className="flex items-center justify-between py-2"><span>{d.filename} <span className="text-xs text-slate-500">({pretty(d.kind)}, {(d.size_bytes / 1024).toFixed(0)} KB)</span></span><Button variant="secondary" onClick={() => openSigned(`/applications/${id}/documents/${d.id}/url`)}>Download</Button></li>)}</ul>}
        </Card>
        <p className="text-xs text-slate-500">{a.ai_disclosure}</p>
      </>}

      {tab === "cv" && <Card title="Tailored CV (built only from your profile)">
        {!cv ? <p className="text-sm text-slate-500">No CV generated yet.</p> : <div className="space-y-3 text-sm">
          <div><div className="text-lg font-bold">{cv.header.name}</div><div className="text-slate-600">{[cv.header.email, cv.header.phone, cv.header.location, ...(cv.header.links || [])].filter(Boolean).join(" · ")}</div></div>
          {cv.summary && <div><div className="label">Summary</div><p>{cv.summary}</p></div>}
          <div><div className="label">Skills</div><Chips items={(cv.skills || []).map((s: any) => (typeof s === "string" ? s : s.name))} tone="blue" /></div>
          <div><div className="label">Experience</div>{(cv.experience || []).map((e: any, i: number) => <div key={i} className="mb-2"><b>{e.title}</b> · {e.company} <span className="text-slate-500">{e.start_date} – {e.is_current ? "Present" : e.end_date}</span><ul className="list-disc pl-5">{(e.bullets || []).map((b: string, k: number) => <li key={k}>{b}</li>)}</ul></div>)}</div>
          <div><div className="label">Education</div>{(cv.education || []).map((e: any, i: number) => <div key={i}>{e.degree} {e.field && `in ${e.field}`} · {e.institution} <span className="text-slate-500">{e.end_date} {e.grade}</span></div>)}</div>
          {cv.projects?.length > 0 && <div><div className="label">Projects</div>{cv.projects.map((p: any, i: number) => <div key={i} className="mb-1"><b>{p.name}</b> — {p.description}</div>)}</div>}
        </div>}
      </Card>}

      {tab === "letter" && <Card title="Cover letter" actions={<Button onClick={saveLetter} disabled={busy || !a.cover_letter}>Save edits</Button>}>
        {!a.cover_letter ? <p className="text-sm text-slate-500">No cover letter for this application.</p> : <>
          <textarea className="input font-serif" rows={16} value={letter} onChange={(e) => setLetter(e.target.value)} />
          <p className="mt-2 text-xs text-slate-500">Edits are re-checked automatically. A letter that mentions another company or claims something not in your profile will be blocked.</p></>}
      </Card>}

      {tab === "email" && <Card title="Application email" actions={<Button onClick={saveEmail} disabled={busy || !em}>Save edits</Button>}>
        {!em ? <p className="text-sm text-slate-500">No email draft. {a.has_url ? "This job uses an application link." : "Add an application email to the job."}</p> : <div className="space-y-3">
          <Field label="To"><input className="input" value={em.to_address} onChange={(e) => setEm({ ...em, to_address: e.target.value })} /></Field>
          <Field label="Send from"><select className="input" value={em.email_account_id} onChange={(e) => setEm({ ...em, email_account_id: e.target.value })}><option value="">Default account</option>{(accounts.data || []).map((x) => <option key={x.id} value={x.id}>{x.address} ({x.provider})</option>)}</select></Field>
          <Field label="Subject"><input className="input" value={em.subject} onChange={(e) => setEm({ ...em, subject: e.target.value })} /></Field>
          <Field label="Body"><textarea className="input" rows={12} value={em.body} onChange={(e) => setEm({ ...em, body: e.target.value })} /></Field>
          <p className="text-xs text-slate-500">Attachments: {a.documents.filter((d: any) => a.email?.attachment_doc_ids?.includes(d.id)).map((d: any) => d.filename).join(", ") || "none selected"}</p></div>}
      </Card>}

      {tab === "track" && <>
        <Card title="Status">
          <div className="flex flex-wrap items-center gap-2"><Badge tone={statusTone(a.status)}>{pretty(a.status)}</Badge>
            {["sent", "application_confirmed", "interview", "offer", "rejected", "withdrawn"].includes(a.status) && TRACK.filter((s) => s !== a.status).map((s) => <Button key={s} variant="secondary" disabled={busy} onClick={() => setStatus(s)}>→ {pretty(s)}</Button>)}</div>
          <p className="mt-2 text-xs text-slate-500">Use these to record real outcomes. Statuses are your own records, not employer decisions.</p>
        </Card>
        <Card title="Notes & reminder" actions={<Button onClick={saveTrack} disabled={busy}>Save</Button>}>
          <Field label="Notes"><textarea className="input" rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
          <div className="mt-3 max-w-xs"><Field label="Follow-up reminder"><input className="input" type="date" value={remind} onChange={(e) => setRemind(e.target.value)} /></Field></div>
        </Card>
        <Card title="Timeline"><ul className="space-y-1 text-sm">{a.events.map((e: any, i: number) => <li key={i}><span className="text-xs text-slate-400">{new Date(e.at).toLocaleString()}</span> · {e.type === "status_change" ? `${pretty(e.from)} → ${pretty(e.to)}` : pretty(e.type)}</li>)}</ul></Card>
      </>}

      <Modal open={regen} onClose={() => setRegen(false)} title="Regenerate">
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Tone"><select className="input" value={ro.tone} onChange={(e) => setRo({ ...ro, tone: e.target.value })}>{["professional", "concise", "technical", "research", "startup"].map((x) => <option key={x}>{x}</option>)}</select></Field>
          <Field label="Language"><select className="input" value={ro.language} onChange={(e) => setRo({ ...ro, language: e.target.value })}><option value="en">English</option><option value="bn">বাংলা</option></select></Field>
          <Field label="Template"><select className="input" value={ro.template} onChange={(e) => setRo({ ...ro, template: e.target.value })}>{["classic", "modern", "compact"].map((x) => <option key={x}>{x}</option>)}</select></Field>
          <Field label="Pages"><select className="input" value={ro.pages} onChange={(e) => setRo({ ...ro, pages: Number(e.target.value) })}><option value={1}>1</option><option value={2}>2</option></select></Field>
        </div>
        <p className="mt-2 text-xs text-slate-500">Regenerating replaces the draft and resets approval. Your manual edits will be lost.</p>
        <div className="mt-3 flex justify-end gap-2"><Button variant="secondary" onClick={() => setRegen(false)}>Cancel</Button><Button onClick={regenerate}>Regenerate</Button></div>
      </Modal>
      <SendDialog ids={sendIds} onClose={() => setSendIds([])} onDone={reload} />
    </>
  );
}
