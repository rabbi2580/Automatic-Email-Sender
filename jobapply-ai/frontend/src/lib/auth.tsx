"use client";
import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";
import { api, tokens } from "./api";

export type User = { id: string; email: string; full_name: string; role: string; email_verified: boolean; locale: string; ai_training_opt_in: boolean };

const Ctx = createContext<{ user: User | null; loading: boolean; reload: () => Promise<void>; logout: () => Promise<void> }>({ user: null, loading: true, reload: async () => {}, logout: async () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    if (!tokens.has()) { setUser(null); setLoading(false); return; }
    try { setUser(await api<User>("/auth/me")); } catch { setUser(null); }
    setLoading(false);
  }, []);
  useEffect(() => { reload(); }, [reload]);
  const logout = async () => {
    try { await api("/auth/logout", { method: "POST", body: { refresh_token: tokens.refresh() || "" } }); } catch { /* token may already be invalid */ }
    tokens.clear(); setUser(null); location.href = "/login";
  };
  return <Ctx.Provider value={{ user, loading, reload, logout }}>{children}</Ctx.Provider>;
}
export const useAuth = () => useContext(Ctx);
