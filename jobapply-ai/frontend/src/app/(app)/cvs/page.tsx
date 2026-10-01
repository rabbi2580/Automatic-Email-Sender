"use client";
import { useRef, useState } from "react";
import { api, openSigned } from "@/lib/api";
import { Badge, Button, Card, Empty, ErrorBox, Spinner, statusTone, useLoad, useToast, pretty } from "@/components/ui";

type Resume = { id: string; filename: string; label: string; size_bytes: number; status: string; status_reason: string; is_master: boolean; created_at: string; duplicate?: boolean };
type Version = { id: string; label: string; role_type: string; template: string; application_id: string | null; created_at: string; target: string; company: string };

export default function CVs() {
  const toast = useToast();
  const list = useLoad(() => api<Resume[]>("/resumes"));
  const versions = useLoad(() => api<Version[]>("/resumes/versions"));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const input = useRef<HTMLInputElement>(null);

  async function upload(file: File) {
    setBusy(true); setErr(null);
    try {
      const fd = new FormData(); fd.append("file", file);
      const r = await api<Resume>("/resumes/upload", { form: fd });
      toast(r.duplicate ? "You already uploaded this exact file." : r.status === "requires_review" ? "Uploaded. Please review the extracted profile." : "CV uploaded and parsed.");
      await list.reload();
    } catch (e) { setErr(e); }
    setBusy(false); if (input.current) input.current.value = "";
  }
  async function del(r: Resume) {
    if (!confirm("Delete this CV file permanently? The structured profile is kept unless you clear it from Profile.")) return;
    try { await api(`/resumes/${r.id}`, { method: "DELETE" }); await list.reload(); } catch (e) { toast((e as Error).message, "err"); }
  }
  async function reparse(r: Resume) {
    try { await api(`/resumes/${r.id}/reparse`, { method: "POST" }); toast("Re-parsing started."); await list.reload(); } catch (e) { toast((e as Error).message, "err"); }
  }
  return (
    <>
      <h1 className="text-xl font-bold">My CVs</h1>
      <Card title="Upload a CV" actions={<Button disabled={busy} onClick={() => input.current?.click()}>{busy ? "Uploading…" : "Choose PDF / DOCX"}</Button>}>
        <input ref={input} type="file" hidden accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        <p className="text-sm text-slate-600">Your original file is stored unchanged. We extract a structured profile from it; tailored CVs are built only from facts in that profile.</p>
        <div className="mt-2"><ErrorBox error={err} /></div>
      </Card>
      <Card title="Uploaded CVs">
        {list.loading ? <Spinner /> : list.error ? <ErrorBox error={list.error} onRetry={list.reload} /> : !list.data?.length ? <Empty title="No CV yet">Upload a PDF or DOCX to build your profile.</Empty> :
          <ul className="divide-y">{list.data.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <div><div className="font-medium">{r.filename}</div><div className="text-xs text-slate-500">{(r.size_bytes / 1024).toFixed(0)} KB · {new Date(r.created_at).toLocaleString()}</div>
                {r.status_reason && <div className="text-xs text-amber-700">{r.status_reason}</div>}</div>
              <div className="flex items-center gap-2"><Badge tone={statusTone(r.status)}>{pretty(r.status)}</Badge>
                <Button variant="secondary" onClick={() => openSigned(`/resumes/${r.id}/download`)}>Download</Button>
                <Button variant="secondary" onClick={() => reparse(r)}>Re-parse</Button>
                <Button variant="ghost" onClick={() => del(r)}>Delete</Button></div>
            </li>))}</ul>}
      </Card>
      <Card title="Tailored CV versions">
        {versions.loading ? <Spinner /> : !versions.data?.length ? <p className="text-sm text-slate-500">Tailored CVs appear here once you generate applications.</p> :
          <ul className="divide-y text-sm">{versions.data.map((v) => <li key={v.id} className="flex justify-between py-2"><span>{v.label || v.target} <span className="text-slate-500">· {v.company}</span></span>
            <span className="text-xs text-slate-500">{v.template} · {new Date(v.created_at).toLocaleDateString()}</span></li>)}</ul>}
      </Card>
    </>
  );
}
