import type { Metadata } from "next";
import Shell from "@/components/Shell";
export const metadata: Metadata = { robots: { index: false, follow: false }, title: "Workspace" };
export default function AppLayout({ children }: { children: React.ReactNode }) { return <Shell>{children}</Shell>; }
