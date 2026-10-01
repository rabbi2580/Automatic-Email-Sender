"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Badge, Button, ErrorBox, Modal, Spinner } from "./ui";

/* eslint-disable @typescript-eslint/no-explicit-any */
/** Two-step send: server preview (recipients, subject, attachments, signed token) → explicit confirmation. Nothing is sent before the checkbox + button. */
export default function SendDialog({ ids, onClose, onDone }: { ids: string[]; onClose: () => void; onDone: () => void }) {
  const [preview, setPreview] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<any[] | null>(null);

  useEffect(() => {
    if (!ids.length) return;
    setPreview(null); setErr(null); setResults(null); setOk(false);
    api<any>("/applications/send/preview", { body: { application_ids: ids } }).then(setPreview).catch(setErr);
  }, [ids]);

  async function send() {
    setBusy(true); setErr(null);
    try {
      const r = await api<any>("/applications/send", { body: { application_ids: preview.items.filter((i: any) => !i.blocked).map((i: any) => i.application_id), confirmation_token: preview.confirmation_token, confirm: true } });
      setResults(r.results); onDone();
    } catch (e) { setErr(e); }
    setBusy(false);
  }
  return (
    <Modal open={ids.length > 0} onClose={onClose} title={results ? "Send results" : "Confirm sending"} wide>
      <div className="space-y-3">
        <ErrorBox error={err} />
        {!preview && !err && <Spinner />}
        {preview && !results && <>
          <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm">{preview.notice}</div>
          <div className="max-h-72 space-y-2 overflow-y-auto">{preview.items.map((i: any) => (
            <div key={i.application_id} className={`rounded border p-2 text-sm ${i.blocked ? "border-red-200 bg-red-50" : ""}`}>
              <div className="font-medium">{i.position} · {i.company}</div>
              {i.blocked ? <ul className="list-disc pl-5 text-xs text-red-700">{i.problems.map((p: string, k: number) => <li key={k}>{p}</li>)}</ul> :
                <div className="text-xs text-slate-600">From <b>{i.from}</b> → To <b>{i.to}</b><br />Subject: {i.subject}<br />Attachments: {i.attachments.map((a: any) => a.filename).join(", ") || "none"}</div>}
            </div>))}</div>
          <p className="text-xs text-slate-500">Sending allowance remaining — today: {preview.limits.day_remaining}, this hour: {preview.limits.hour_remaining}</p>
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={ok} onChange={(e) => setOk(e.target.checked)} />I have reviewed these applications and confirm they should be sent from my email account now.</label>
          <div className="flex justify-end gap-2"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button disabled={!ok || !preview.count || busy} onClick={send}>{busy ? "Sending…" : `Send ${preview.count} application(s)`}</Button></div>
        </>}
        {results && <>{results.map((r: any, i: number) => <div key={i} className="flex items-center justify-between rounded border p-2 text-sm"><span>{r.application_id.slice(0, 8)}…</span><span><Badge tone={r.status === "sent" ? "green" : "red"}>{r.status}</Badge> {r.error || r.message || ""}</span></div>)}
          <div className="text-right"><Button onClick={onClose}>Done</Button></div></>}
      </div>
    </Modal>
  );
}
