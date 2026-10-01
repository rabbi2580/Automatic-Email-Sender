"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { Badge, Button, Card, Empty, ErrorBox, Field, Spinner, pretty, useLoad, useToast } from "@/components/ui";

/* eslint-disable @typescript-eslint/no-explicit-any */
function Inner() {
  const toast = useToast();
  const sp = useSearchParams();
  const { data, error, loading, reload } = useLoad(() => api<any[]>("/integrations/email"));
  const [consent, setConsent] = useState(false);
  const [smtp, setSmtp] = useState<any>({ address: "", display_name: "", host: "", port: 587, username: "", password: "", security: "starttls" });
  const [showSmtp, setShowSmtp] = useState(false);
  useEffect(() => {
    if (sp.get("connected")) toast(`${pretty(sp.get("connected"))} connected.`);
    if (sp.get("error")) toast("Could not connect that account. Please try again.", "err");
  }, [sp, toast]);

  async function connect(provider: "gmail" | "outlook") {
    try { const r = await api<any>("/integrations/email/connect", { body: { provider, consent } }); location.href = r.authorization_url; } catch (e) { toast((e as Error).message, "err"); }
  }
  async function saveSmtp(e: React.FormEvent) {
    e.preventDefault();
    try { await api("/integrations/email/smtp", { body: { ...smtp, port: Number(smtp.port), consent } }); toast("SMTP account saved (password encrypted)."); setSmtp({ ...smtp, password: "" }); setShowSmtp(false); reload(); } catch (e2) { toast((e2 as Error).message, "err"); }
  }
  async function remove(id: string) { if (!confirm("Disconnect this account? Stored credentials will be deleted.")) return; try { await api(`/integrations/email/${id}`, { method: "DELETE" }); reload(); } catch (e) { toast((e as Error).message, "err"); } }
  async function makeDefault(id: string) { try { await api(`/integrations/email/${id}/default`, { method: "POST" }); reload(); } catch (e) { toast((e as Error).message, "err"); } }
  return (
    <>
      <h1 className="text-xl font-bold">Email accounts</h1>
      <Card title="Connect an account">
        <div className="space-y-3">
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} />I allow JobApply AI to send emails from my account on my behalf, <b>only after I approve and confirm each application</b>. I can disconnect at any time.</label>
          <div className="flex flex-wrap gap-2"><Button disabled={!consent} onClick={() => connect("gmail")}>Connect Gmail</Button><Button disabled={!consent} variant="secondary" onClick={() => connect("outlook")}>Connect Outlook</Button><Button disabled={!consent} variant="secondary" onClick={() => setShowSmtp(!showSmtp)}>Use SMTP</Button></div>
          <p className="text-xs text-slate-500">Gmail and Outlook use the minimum “send” permission only; we cannot read your inbox. Tokens and SMTP passwords are encrypted at rest.</p>
          {showSmtp && <form onSubmit={saveSmtp} className="grid gap-3 rounded-md border p-3 md:grid-cols-2">
            <Field label="Email address"><input className="input" type="email" required value={smtp.address} onChange={(e) => setSmtp({ ...smtp, address: e.target.value })} /></Field>
            <Field label="Display name"><input className="input" value={smtp.display_name} onChange={(e) => setSmtp({ ...smtp, display_name: e.target.value })} /></Field>
            <Field label="SMTP host"><input className="input" required value={smtp.host} onChange={(e) => setSmtp({ ...smtp, host: e.target.value })} /></Field>
            <Field label="Port"><input className="input" type="number" value={smtp.port} onChange={(e) => setSmtp({ ...smtp, port: e.target.value })} /></Field>
            <Field label="Username"><input className="input" required autoComplete="off" value={smtp.username} onChange={(e) => setSmtp({ ...smtp, username: e.target.value })} /></Field>
            <Field label="Password / app password"><input className="input" type="password" required autoComplete="new-password" value={smtp.password} onChange={(e) => setSmtp({ ...smtp, password: e.target.value })} /></Field>
            <Field label="Security"><select className="input" value={smtp.security} onChange={(e) => setSmtp({ ...smtp, security: e.target.value })}><option value="starttls">STARTTLS</option><option value="ssl">SSL/TLS</option><option value="none">None (not recommended)</option></select></Field>
            <div className="flex items-end"><Button disabled={!consent}>Save SMTP account</Button></div>
          </form>}
        </div>
      </Card>
      <Card title="Connected accounts">
        {loading ? <Spinner /> : error ? <ErrorBox error={error} onRetry={reload} /> : !data?.length ? <Empty title="No email account connected">You need one to send applications by email.</Empty> :
          <ul className="divide-y">{data.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <div><b>{a.address}</b> <span className="text-slate-500">· {a.provider}</span><div className="text-xs text-slate-500">{a.last_used_at ? `Last used ${new Date(a.last_used_at).toLocaleDateString()}` : "Never used"}</div></div>
              <div className="flex items-center gap-2">{a.is_default && <Badge tone="blue">Default</Badge>}<Badge tone={a.status === "active" ? "green" : "red"}>{a.status === "needs_reauth" ? "Reconnect needed" : pretty(a.status)}</Badge>
                {!a.is_default && <Button variant="secondary" onClick={() => makeDefault(a.id)}>Make default</Button>}<Button variant="ghost" onClick={() => remove(a.id)}>Disconnect</Button></div>
            </li>))}</ul>}
      </Card>
    </>
  );
}
export default function EmailPage() { return <Suspense fallback={<Spinner />}><Inner /></Suspense>; }
