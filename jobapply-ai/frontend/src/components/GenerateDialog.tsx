"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Button, Field, Modal, useToast } from "@/components/ui";

/* eslint-disable @typescript-eslint/no-explicit-any */
/* ---------- generation options dialog ---------- */
export default function GenerateDialog({ open, ids, onClose }: { open: boolean; ids: string[]; onClose: () => void }) {
  const toast = useToast();
  const [o, setO] = useState<any>({ tone: "professional", language: "en", template: "classic", font: "sans", pages: 1, include_cover_letter: true });
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    try { const r = await api<any>("/applications/generate", { body: { job_ids: ids, ...o } }); toast(`${r.applications.length} application(s) prepared.`); onClose(); location.href = "/applications"; }
    catch (e) { toast((e as Error).message, "err"); }
    setBusy(false);
  }
  return (
    <Modal open={open} onClose={onClose} title={`Generate ${ids.length} application(s)`}>
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Tone"><select className="input" value={o.tone} onChange={(e) => setO({ ...o, tone: e.target.value })}>{["professional", "concise", "technical", "research", "startup"].map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field label="Language"><select className="input" value={o.language} onChange={(e) => setO({ ...o, language: e.target.value })}><option value="en">English</option><option value="bn">বাংলা</option></select></Field>
        <Field label="CV template"><select className="input" value={o.template} onChange={(e) => setO({ ...o, template: e.target.value })}>{["classic", "modern", "compact"].map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field label="Font"><select className="input" value={o.font} onChange={(e) => setO({ ...o, font: e.target.value })}><option value="sans">Sans</option><option value="serif">Serif</option></select></Field>
        <Field label="Max pages"><select className="input" value={o.pages} onChange={(e) => setO({ ...o, pages: Number(e.target.value) })}><option value={1}>1</option><option value={2}>2</option></select></Field>
        <label className="flex items-end gap-2 pb-2 text-sm"><input type="checkbox" checked={o.include_cover_letter} onChange={(e) => setO({ ...o, include_cover_letter: e.target.checked })} />Include cover letter</label>
      </div>
      <div className="mt-4 flex justify-end gap-2"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={go} disabled={busy}>{busy ? "Generating…" : "Generate"}</Button></div>
    </Modal>
  );
}
