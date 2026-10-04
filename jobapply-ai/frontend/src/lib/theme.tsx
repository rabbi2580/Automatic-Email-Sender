"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";

export type Theme = "light" | "dark";
const ThemeCtx = createContext<{ theme: Theme; toggle: () => void }>({ theme: "light", toggle: () => {} });

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");
  useEffect(() => {
    const saved = localStorage.getItem("jaa_theme") as Theme | null;
    const next = saved === "dark" || saved === "light" ? saved : "light";
    setTheme(next); document.documentElement.dataset.theme = next; document.documentElement.classList.toggle("theme-dark", next === "dark");
  }, []);
  const toggle = () => setTheme((current) => {
    const next = current === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next; document.documentElement.classList.toggle("theme-dark", next === "dark"); localStorage.setItem("jaa_theme", next); return next;
  });
  return <ThemeCtx.Provider value={{ theme, toggle }}>{children}</ThemeCtx.Provider>;
}
export const useTheme = () => useContext(ThemeCtx);
