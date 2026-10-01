"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Badge, Button, Card, ErrorBox, Field, ScoreBar, Spinner, useLoad, useToast } from "@/components/ui";

/* eslint-disable @typescript-eslint/no-explicit-any */
type P = any;
const csv = (a?: string[]) => (a || []).join(", ");
const unCsv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const lines = (a?: string[]) => (a || []).join("\n");
const unLines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

export default function Profile() {
  const toast = useToast();
  const { data, error, loading, reload } = useLoad(() => api<P>("/profile"));
  const [p, setP] = useState<P | null>(null);
  const [saving, setSaving] = useState(false);
  const [skill, setSkill] = useState("");
  useEffect(() => { if (data) setP(JSON.parse(JSON.stringify(data))); }, [data]);
  if (loading || !p) return error ? <ErrorBox error={error} onRetry={reload} /> : <Spinner />;

  const set = (k: string, v: any) => setP({ ...p, [k]: v });
  const setItem = (key: string, i: number, patch: any) => set(key, p[key].map((x: any, j: number) => (j === i ? { ...x, ...patch } : x)));
  const rm = (key: string, i: number) => set(key, p[key].filter((_: any, j: number) => j !== i));

  async function save() {
    setSaving(true);
    try {
      const body = {
        ...p,
        skills: p.skills.map((s: any) => ({ name: s.name, category: s.category || "technical" })),
      };
      await api("/profile/structured", { method: "PUT", body });
      toast("Profile saved. Matches were recomputed.");
      await reload();
    } catch (e) { toast((e as Error).message, "err"); }
    setSaving(false);
  }
  const c = p.completeness;
  const links = p.links || {};
  const experienceSection = (title: string, kind: string) => (
    <Card title={title} actions={<Button variant="secondary" onClick={() => set("experiences", [...p.experiences, { kind, company: "", title: "", location: "", start_date: "", end_date: "", is_current: false, bullets: [], technologies: [] }])}>Add</Button>}>
      {p.experiences.map((x: any, i: number) => ({ x, i })).filter((entry: { x: any; i: number }) => entry.x.kind === kind).map(({ x, i }: { x: any; i: number }) => (
        <div key={i} className="mb-3 grid gap-2 rounded-md border p-3 md:grid-cols-3">
          <Field label="Title"><input className="input" value={x.title} onChange={(e) => setItem("experiences", i, { title: e.target.value })} /></Field>
          <Field label="Organization"><input className="input" value={x.company} onChange={(e) => setItem("experiences", i, { company: e.target.value })} /></Field>
          <Field label="Location"><input className="input" value={x.location} onChange={(e) => setItem("experiences", i, { location: e.target.value })} /></Field>
          <Field label="Start"><input className="input" value={x.start_date} onChange={(e) => setItem("experiences", i, { start_date: e.target.value })} /></Field>
          <Field label="End"><input className="input" value={x.end_date} disabled={x.is_current} onChange={(e) => setItem("experiences", i, { end_date: e.target.value })} /></Field>
          <label className="flex items-end gap-2 pb-2 text-sm"><input type="checkbox" checked={x.is_current} onChange={(e) => setItem("experiences", i, { is_current: e.target.checked })} />Current</label>
          <div className="md:col-span-3"><Field label="Details (one per line)"><textarea className="input" rows={3} value={lines(x.bullets)} onChange={(e) => setItem("experiences", i, { bullets: unLines(e.target.value) })} /></Field></div>
          <div className="md:col-span-3"><Field label="Technologies (comma separated)"><input className="input" value={csv(x.technologies)} onChange={(e) => setItem("experiences", i, { technologies: unCsv(e.target.value) })} /></Field></div>
          <div className="md:col-span-3 text-right"><Button variant="ghost" onClick={() => rm("experiences", i)}>Remove</Button></div>
        </div>))}
    </Card>
  );
  const projectSection = (title: string, kind: string) => (
    <Card title={title} actions={<Button variant="secondary" onClick={() => set("projects", [...p.projects, { name: "", description: "", bullets: [], technologies: [], url: "", kind }])}>Add</Button>}>
      {p.projects.map((x: any, i: number) => ({ x, i })).filter((entry: { x: any; i: number }) => entry.x.kind === kind).map(({ x, i }: { x: any; i: number }) => (
        <div key={i} className="mb-3 grid gap-2 rounded-md border p-3 md:grid-cols-2">
          <Field label="Name"><input className="input" value={x.name} onChange={(e) => setItem("projects", i, { name: e.target.value })} /></Field>
          <div className="md:col-span-2"><Field label="Description"><textarea className="input" rows={3} value={x.description} onChange={(e) => setItem("projects", i, { description: e.target.value })} /></Field></div>
          <div className="md:col-span-2"><Field label="Technologies (comma separated)"><input className="input" value={csv(x.technologies)} onChange={(e) => setItem("projects", i, { technologies: unCsv(e.target.value) })} /></Field></div>
          <div className="md:col-span-2 text-right"><Button variant="ghost" onClick={() => rm("projects", i)}>Remove</Button></div>
        </div>))}
    </Card>
  );
  return (
    <div className="profile-page">
      <div className="profile-heading">
        <div><p className="eyebrow">Candidate workspace</p><h1>My Profile</h1></div>
        <Button onClick={save} disabled={saving}>{saving ? "Saving…" : "Save profile"}</Button>
      </div>
      {!p.resume && <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-sm">No CV uploaded yet. <Link className="underline" href="/cvs">Upload one</Link> to fill this in automatically, or enter details by hand.</div>}
      <Card className="profile-completion" title={`Profile completeness: ${c.percent}%`}><ScoreBar value={c.percent} />{c.missing.length > 0 && <p className="mt-2 text-xs text-slate-500">Missing: {c.missing.join(", ").replace(/_/g, " ")}</p>}</Card>

      <Card title="Personal Information / Contact Information">
        <div className="grid gap-3 md:grid-cols-2">
          {([["full_name", "Full name"], ["email", "Email"], ["phone", "Phone"], ["location", "Location"]] as const).map(([k, l]) =>
            <Field key={k} label={l}><input className="input" value={p[k] || ""} onChange={(e) => set(k, e.target.value)} /></Field>)}
          <Field label="LinkedIn"><input className="input" value={links.linkedin || ""} onChange={(e) => set("links", { ...links, linkedin: e.target.value })} /></Field>
          <Field label="GitHub"><input className="input" value={links.github || ""} onChange={(e) => set("links", { ...links, github: e.target.value })} /></Field>
          <div className="md:col-span-2"><Field label="Portfolio / other links"><input className="input" value={csv(Array.isArray(links.other) ? links.other : links.other ? [links.other] : [])} onChange={(e) => set("links", { ...links, other: unCsv(e.target.value) })} /></Field></div>
        </div>
      </Card>

      <Card title="Professional Summary / Career Objective">
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Headline"><input className="input" value={p.headline || ""} onChange={(e) => set("headline", e.target.value)} /></Field>
          <Field label="Years of experience"><input className="input" type="number" min={0} step={0.5} value={p.years_experience ?? ""} onChange={(e) => set("years_experience", e.target.value === "" ? null : Number(e.target.value))} /></Field>
          <div className="md:col-span-2"><Field label="Summary"><textarea className="input" rows={4} value={p.summary || ""} onChange={(e) => set("summary", e.target.value)} /></Field></div>
        </div>
      </Card>

      <Card title="Job Preferences">
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Target roles (comma separated)"><input className="input" value={csv(p.target_roles)} onChange={(e) => set("target_roles", unCsv(e.target.value))} /></Field>
          <Field label="Preferred locations (comma separated)"><input className="input" value={csv(p.preferred_locations)} onChange={(e) => set("preferred_locations", unCsv(e.target.value))} /></Field>
          <Field label="Work preference"><select className="input" value={p.work_preference || "any"} onChange={(e) => set("work_preference", e.target.value)}>{["any", "onsite", "hybrid", "remote"].map((o) => <option key={o}>{o}</option>)}</select></Field>
        </div>
      </Card>

      <Card title={`Skills (${p.skills.length})`}>
        <div className="flex flex-wrap gap-1">{p.skills.map((s: any, i: number) => <span key={i} className="inline-flex items-center gap-1"><Badge tone="blue">{s.name}</Badge><button aria-label={`Remove ${s.name}`} className="text-xs text-slate-400 hover:text-red-600" onClick={() => rm("skills", i)}>✕</button></span>)}</div>
        <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); const n = skill.trim(); if (n && !p.skills.some((s: any) => s.name.toLowerCase() === n.toLowerCase())) set("skills", [...p.skills, { name: n, category: "technical" }]); setSkill(""); }}>
          <input className="input" placeholder="Add a skill you really have" value={skill} onChange={(e) => setSkill(e.target.value)} /><Button variant="secondary">Add</Button></form>
      </Card>

      {experienceSection("Work Experience", "work")}
      {experienceSection("Internship Experience", "internship")}
      {experienceSection("Volunteer Experience", "volunteer")}

      <Card title="Education" actions={<Button variant="secondary" onClick={() => set("educations", [...p.educations, { institution: "", degree: "", field: "", level: "", start_date: "", end_date: "", grade: "", details: [] }])}>Add</Button>}>
        {p.educations.map((x: any, i: number) => (
          <div key={i} className="mb-3 grid gap-2 rounded-md border p-3 md:grid-cols-3">
            <Field label="Institution"><input className="input" value={x.institution} onChange={(e) => setItem("educations", i, { institution: e.target.value })} /></Field>
            <Field label="Degree"><input className="input" value={x.degree} onChange={(e) => setItem("educations", i, { degree: e.target.value })} /></Field>
            <Field label="Field"><input className="input" value={x.field} onChange={(e) => setItem("educations", i, { field: e.target.value })} /></Field>
            <Field label="Start"><input className="input" value={x.start_date} onChange={(e) => setItem("educations", i, { start_date: e.target.value })} /></Field>
            <Field label="End"><input className="input" value={x.end_date} onChange={(e) => setItem("educations", i, { end_date: e.target.value })} /></Field>
            <Field label="Grade / CGPA"><input className="input" value={x.grade} onChange={(e) => setItem("educations", i, { grade: e.target.value })} /></Field>
            <div className="md:col-span-3 text-right"><Button variant="ghost" onClick={() => rm("educations", i)}>Remove</Button></div>
          </div>))}
      </Card>

      {projectSection("Projects", "project")}
      {projectSection("Research", "research")}

      <Card title="Publications">
        <Field label="One publication per line"><textarea className="input" rows={3} value={lines(p.publications)} onChange={(e) => set("publications", unLines(e.target.value))} /></Field>
      </Card>

      <Card title="Certifications / Courses" actions={<Button variant="secondary" onClick={() => set("certifications", [...p.certifications, { name: "", issuer: "", date: "" }])}>Add</Button>}>
        {p.certifications.map((x: any, i: number) => (
          <div key={i} className="mb-2 grid gap-2 md:grid-cols-4">
            <input className="input md:col-span-2" placeholder="Name" value={x.name} onChange={(e) => setItem("certifications", i, { name: e.target.value })} />
            <input className="input" placeholder="Issuer" value={x.issuer} onChange={(e) => setItem("certifications", i, { issuer: e.target.value })} />
            <div className="flex gap-1"><input className="input" placeholder="Date" value={x.date} onChange={(e) => setItem("certifications", i, { date: e.target.value })} /><Button variant="ghost" onClick={() => rm("certifications", i)}>✕</Button></div>
          </div>))}
      </Card>

      <Card title="Achievements / Awards">
        <Field label="One item per line"><textarea className="input" rows={3} value={lines(p.achievements)} onChange={(e) => set("achievements", unLines(e.target.value))} /></Field>
      </Card>

      <Card title="Extracurricular Activities">
        <Field label="One activity per line"><textarea className="input" rows={3} value={lines(p.extracurriculars)} onChange={(e) => set("extracurriculars", unLines(e.target.value))} /></Field>
      </Card>

      <Card title="Languages">
        <Field label="Comma separated"><input className="input" value={csv(p.languages)} onChange={(e) => set("languages", unCsv(e.target.value))} /></Field>
      </Card>

      <Card title="Strengths & Interests">
        <Field label="One item per line"><textarea className="input" rows={3} value={lines(p.strengths)} onChange={(e) => set("strengths", unLines(e.target.value))} /></Field>
      </Card>

      <Card title="References">
        <Field label="One reference per line"><textarea className="input" rows={3} value={lines(p.references)} onChange={(e) => set("references", unLines(e.target.value))} /></Field>
      </Card>

      <div className="text-right"><Button onClick={save} disabled={saving}>{saving ? "Saving…" : "Save profile"}</Button></div>
    </div>
  );
}
