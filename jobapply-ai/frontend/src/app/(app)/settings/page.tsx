"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { Button, Card, ErrorBox, Field, Spinner, pretty, useLoad, useToast } from "@/components/ui";

/* eslint-disable @typescript-eslint/no-explicit-any */
const DIMS = ["skills", "experience", "education", "responsibilities", "technology", "role", "location"];
const TH = ["strong", "potential", "weak"];

export default function Settings() {
  const toast = useToast();
  const { user, reload: reloadUser } = useAuth();
  const { setLocale } = useI18n();
  const { data, error, loading, reload } = useLoad(() => api<any>("/settings"));
  const [s, setS] = useState<any>(null);
  const [name, setName] = useState("");
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  useEffect(() => { if (data) setS(JSON.parse(JSON.stringify(data))); }, [data]);
  useEffect(() => { if (user) setName(user.full_name); }, [user]);
  if (loading || !s) return error ? <ErrorBox error={error} onRetry={reload} /> : <Spinner />;

  const total = DIMS.reduce((a, k) => a + Number(s.weights[k] || 0), 0);
  async function save() {
    try {
      await api("/settings", { method: "PUT", body: { weights: s.weights, thresholds: s.thresholds, tone: s.tone, language: s.language, cv_template: s.cv_template, cv_font: s.cv_font, cv_pages: Number(s.cv_pages), cv_style: s.cv_style, include_cover_letter: s.include_cover_letter, reminder_days_before_deadline: Number(s.reminder_days_before_deadline) } });
      toast("Settings saved."); reload();
    } catch (e) { toast((e as Error).message, "err"); }
  }
  async function saveAccount() {
    try { const l = s.language === "bn" ? "bn" : "en"; await api("/auth/me", { method: "PATCH", body: { full_name: name, locale: l } }); setLocale(l); await reloadUser(); toast("Account updated."); } catch (e) { toast((e as Error).message, "err"); }
  }
  async function changePw(e: React.FormEvent) {
    e.preventDefault();
    try { await api("/auth/change-password", { body: pw }); toast("Password changed. Other sessions were signed out."); setPw({ current_password: "", new_password: "" }); } catch (e2) { toast((e2 as Error).message, "err"); }
  }
  return (
    <>
      <div className="flex items-center justify-between"><h1 className="text-xl font-bold">Settings</h1><Button onClick={save}>Save settings</Button></div>
      <Card title="Matching weights" actions={<Button variant="ghost" onClick={() => setS({ ...s, weights: { skills: 30, experience: 20, education: 10, responsibilities: 15, technology: 10, role: 10, location: 5 } })}>Reset</Button>}>
        <p className="mb-3 text-xs text-slate-500">Weights are relative (they are normalised, so they don’t need to add to 100). Current sum: {total}. Dimensions a job post gives no information about are skipped automatically.</p>
        <div className="grid gap-3 md:grid-cols-2">{DIMS.map((k) => <label key={k} className="block text-sm"><span className="flex justify-between"><span>{pretty(k)}</span><span className="text-slate-500">{s.weights[k]}{total ? ` (${Math.round((100 * s.weights[k]) / total)}%)` : ""}</span></span>
          <input type="range" className="w-full" min={0} max={100} value={s.weights[k]} onChange={(e) => setS({ ...s, weights: { ...s.weights, [k]: Number(e.target.value) } })} /></label>)}</div>
      </Card>
      <Card title="Classification thresholds">
        <div className="grid gap-3 md:grid-cols-3">{TH.map((k) => <Field key={k} label={`${pretty(k)} match from (score ≥)`}><input className="input" type="number" min={0} max={100} value={s.thresholds[k]} onChange={(e) => setS({ ...s, thresholds: { ...s.thresholds, [k]: Number(e.target.value) } })} /></Field>)}</div>
        <p className="mt-2 text-xs text-slate-500">Must satisfy strong ≥ potential ≥ weak. Below “weak” is “not suitable”. After saving, use “Recompute” on the Matches page.</p>
      </Card>
      <Card title="Generation defaults">
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="Tone"><select className="input" value={s.tone} onChange={(e) => setS({ ...s, tone: e.target.value })}>{["professional", "concise", "technical", "research", "startup"].map((x) => <option key={x}>{x}</option>)}</select></Field>
          <Field label="Language (UI + documents)"><select className="input" value={s.language} onChange={(e) => setS({ ...s, language: e.target.value })}><option value="en">English</option><option value="bn">বাংলা</option></select></Field>
          <Field label="CV template"><select className="input" value={s.cv_template} onChange={(e) => setS({ ...s, cv_template: e.target.value })}>{["classic", "modern", "compact"].map((x) => <option key={x}>{x}</option>)}</select></Field>
          <Field label="CV font"><select className="input" value={s.cv_font} onChange={(e) => setS({ ...s, cv_font: e.target.value })}><option value="sans">Sans</option><option value="serif">Serif</option></select></Field>
          <Field label="CV pages"><select className="input" value={s.cv_pages} onChange={(e) => setS({ ...s, cv_pages: e.target.value })}><option value={1}>1</option><option value={2}>2</option></select></Field>
          <Field label="Remind me N days before a deadline"><input className="input" type="number" min={0} max={30} value={s.reminder_days_before_deadline} onChange={(e) => setS({ ...s, reminder_days_before_deadline: e.target.value })} /></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!s.include_cover_letter} onChange={(e) => setS({ ...s, include_cover_letter: e.target.checked })} />Include a cover letter by default</label>
        </div>
      </Card>
      <Card title="Account" actions={<Button variant="secondary" onClick={saveAccount}>Save</Button>}>
        <div className="max-w-sm"><Field label="Full name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field></div>
      </Card>
      <Card title="Change password">
        <form onSubmit={changePw} className="grid max-w-md gap-3"><Field label="Current password"><input className="input" type="password" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} /></Field>
          <Field label="New password (10+ characters)"><input className="input" type="password" minLength={10} autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></Field><div><Button variant="secondary">Change password</Button></div></form>
      </Card>
    </>
  );
}
