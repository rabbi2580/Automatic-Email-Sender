"use client";
import { useState } from "react";
import { api, downloadJson } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button, Card, Field, Spinner, useLoad, useToast } from "@/components/ui";

/* eslint-disable @typescript-eslint/no-explicit-any */
export default function Privacy() {
  const toast = useToast();
  const { user, reload, logout } = useAuth();
  const audit = useLoad(() => api<any[]>("/privacy/audit-log"));
  const [confirm, setConfirm] = useState("");
  const [pw, setPw] = useState("");
  async function exportAll() { try { await downloadJson("/privacy/export", "jobapply-export.json"); } catch (e) { toast((e as Error).message, "err"); } }
  async function training(v: boolean) { try { await api("/privacy/ai-training", { method: "PUT", body: { opt_in: v } }); await reload(); toast("Preference saved."); } catch (e) { toast((e as Error).message, "err"); } }
  async function delHistory() {
    if (!window.confirm("Delete all application history (emails, letters, generated documents)? Your profile and jobs are kept.")) return;
    try { await api("/privacy/application-history", { method: "DELETE" }); toast("Application history deleted."); } catch (e) { toast((e as Error).message, "err"); }
  }
  async function delAccount() {
    try { await api("/privacy/account", { method: "DELETE", body: { confirm: "DELETE MY ACCOUNT", password: pw || null } }); await logout(); } catch (e) { toast((e as Error).message, "err"); }
  }
  return (
    <>
      <h1 className="text-xl font-bold">Privacy &amp; data</h1>
      <Card title="Your data" actions={<Button onClick={exportAll}>Export everything (JSON)</Button>}><p className="text-sm text-slate-600">Download all data we hold about you: profile, CV text, jobs, matches, applications and emails. Credentials are never included.</p></Card>
      <Card title="AI training">
        <p className="text-sm text-slate-600">By default your documents are <b>never</b> used to train any model. You can opt in to help improve the service.</p>
        <label className="mt-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={!!user?.ai_training_opt_in} onChange={(e) => training(e.target.checked)} />Allow my anonymised data to be used for improving AI quality</label>
      </Card>
      <Card title="Third-party processing">
        <p className="text-sm text-slate-600">If the service is configured with an external AI provider, the text of your CV and job posts is sent to that provider only to generate your results. Prompts contain no email credentials. Request/response metadata (not content) is logged for cost and reliability.</p>
      </Card>
      <Card title="Delete application history"><p className="mb-2 text-sm text-slate-600">Removes generated CVs, letters, emails and send logs. This cannot be undone.</p><Button variant="secondary" onClick={delHistory}>Delete application history</Button></Card>
      <Card title="Delete account" className="border-red-200">
        <p className="mb-2 text-sm text-slate-600">Permanently deletes your account, uploaded files, profile, jobs, applications and connected email credentials.</p>
        <div className="grid max-w-md gap-3">
          {user && <Field label="Password (if you set one)"><input className="input" type="password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>}
          <Field label={`Type DELETE MY ACCOUNT to confirm`}><input className="input" value={confirm} onChange={(e) => setConfirm(e.target.value)} /></Field>
          <div><Button variant="danger" disabled={confirm !== "DELETE MY ACCOUNT"} onClick={delAccount}>Permanently delete my account</Button></div>
        </div>
      </Card>
      <Card title="Recent account activity">
        {audit.loading ? <Spinner /> : <ul className="space-y-1 text-xs text-slate-600">{(audit.data || []).slice(0, 30).map((r, i) => <li key={i}>{new Date(r.at).toLocaleString()} · {r.action}{r.ip ? ` · ${r.ip}` : ""}</li>)}</ul>}
      </Card>
    </>
  );
}
