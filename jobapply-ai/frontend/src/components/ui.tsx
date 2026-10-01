"use client";
import { ReactNode, useEffect, useState, createContext, useContext, useCallback } from "react";

export function cx(...a: (string | false | null | undefined)[]) { return a.filter(Boolean).join(" "); }

export function Button({ variant = "primary", className, ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" }) {
  const v = {
    primary: "bg-brand-600 text-white hover:bg-brand-700",
    secondary: "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50",
    danger: "bg-red-600 text-white hover:bg-red-700",
    ghost: "text-slate-700 hover:bg-slate-100",
  }[variant];
  return <button {...p} className={cx("inline-flex items-center justify-center gap-1 rounded-md px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50", v, className)} />;
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded-lg border border-slate-200 bg-white p-4 shadow-sm", className)}>
      {(title || actions) && <div className="mb-3 flex items-center justify-between gap-2"><h2 className="text-sm font-semibold text-slate-800">{title}</h2><div className="flex gap-2">{actions}</div></div>}
      {children}
    </section>
  );
}

const tones: Record<string, string> = {
  green: "bg-emerald-100 text-emerald-800", blue: "bg-blue-100 text-blue-800", amber: "bg-amber-100 text-amber-800",
  red: "bg-red-100 text-red-800", gray: "bg-slate-100 text-slate-700", purple: "bg-violet-100 text-violet-800",
};
export function Badge({ tone = "gray", children }: { tone?: keyof typeof tones | string; children: ReactNode }) {
  return <span className={cx("inline-block rounded-full px-2 py-0.5 text-xs font-medium", tones[tone] || tones.gray)}>{children}</span>;
}

export const classTone = (c?: string | null) => ({ strong: "green", potential: "blue", weak: "amber", not_suitable: "red" } as Record<string, string>)[c || ""] || "gray";
export const classLabel = (c?: string | null) => ({ strong: "Strong match", potential: "Potential", weak: "Weak", not_suitable: "Not suitable" } as Record<string, string>)[c || ""] || "—";
export const urgencyTone = (u?: string | null) => (u === "overdue" || u === "urgent" ? "red" : u === "soon" ? "amber" : "gray");
export const statusTone = (s: string) =>
  ({ sent: "blue", application_confirmed: "blue", interview: "green", offer: "green", rejected: "red", withdrawn: "gray", approved: "purple", awaiting_review: "amber", failed: "red" } as Record<string, string>)[s] || "gray";
export const pretty = (s?: string | null) => (s || "").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return <label className="block"><span className="label">{label}</span>{children}{hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}</label>;
}

export function Spinner({ text = "Loading…" }: { text?: string }) {
  return <div role="status" className="flex items-center gap-2 p-6 text-sm text-slate-500"><span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-brand-600" />{text}</div>;
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return <div role="alert" className="flex items-center justify-between rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"><span>{msg}</span>{onRetry && <Button variant="secondary" onClick={onRetry}>Retry</Button>}</div>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center"><p className="font-medium text-slate-700">{title}</p><div className="mt-2 text-sm text-slate-500">{children}</div></div>;
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title} onMouseDown={(e) => e.stopPropagation()}
        className={cx("max-h-[90vh] w-full overflow-y-auto rounded-lg bg-white p-5 shadow-xl", wide ? "max-w-3xl" : "max-w-lg")}>
        <div className="mb-3 flex items-start justify-between"><h3 className="text-lg font-semibold">{title}</h3><button aria-label="Close" className="text-slate-400 hover:text-slate-700" onClick={onClose}>✕</button></div>
        {children}
      </div>
    </div>
  );
}

export function ScoreBar({ value, tone = "bg-brand-600" }: { value: number; tone?: string }) {
  return <div className="h-2 w-full rounded bg-slate-100"><div className={cx("h-2 rounded", tone)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div>;
}

export function Chips({ items, tone = "gray" }: { items?: string[] | null; tone?: string }) {
  if (!items?.length) return <span className="text-sm text-slate-400">—</span>;
  return <div className="flex flex-wrap gap-1">{items.map((s, i) => <Badge key={i} tone={tone}>{s}</Badge>)}</div>;
}

// ---- toasts
type Toast = { id: number; kind: "ok" | "err"; text: string };
const ToastCtx = createContext<(text: string, kind?: "ok" | "err") => void>(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((text: string, kind: "ok" | "err" = "ok") => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, kind, text }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), 5000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div aria-live="polite" className="fixed bottom-4 right-4 z-[60] space-y-2">
        {items.map((t) => <div key={t.id} className={cx("max-w-sm rounded-md px-4 py-2 text-sm text-white shadow-lg", t.kind === "ok" ? "bg-slate-800" : "bg-red-600")}>{t.text}</div>)}
      </div>
    </ToastCtx.Provider>
  );
}

/** Tiny data hook: load on mount + manual reload, with loading/error state (no silent failures). */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const load = useCallback(async () => { setLoading(true); setError(null); try { setData(await fn()); } catch (e) { setError(e); } setLoading(false); }, deps);
  useEffect(() => { load(); }, [load]);
  return { data, error, loading, reload: load, setData };
}
