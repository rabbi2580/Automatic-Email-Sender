import Link from "next/link";
import StructuredData from "@/components/StructuredData";

export default function Home() {
  return <><StructuredData /><main className="hero-grid min-h-screen overflow-hidden">
    <nav className="mx-auto flex max-w-7xl items-center justify-between px-5 py-6 lg:px-8">
      <Link href="/" className="flex items-center gap-2 text-xl font-extrabold"><span className="grid h-9 w-9 place-items-center rounded-xl bg-indigo-600 text-white">✦</span> JobApply <span className="text-indigo-600">AI</span></Link>
      <div className="flex items-center gap-3"><Link href="/login" className="rounded-xl px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-white">Sign in</Link><Link href="/register" className="rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-bold text-white shadow-lg shadow-indigo-600/20 hover:bg-indigo-700">Get started</Link></div>
    </nav>
    <section className="mx-auto grid max-w-7xl items-center gap-12 px-5 pb-20 pt-16 lg:grid-cols-[1.05fr_.95fr] lg:px-8 lg:pb-28 lg:pt-24">
      <div className="float-in"><div className="mb-5 inline-flex rounded-full border border-indigo-200 bg-white/80 px-3 py-1.5 text-xs font-bold text-indigo-700 shadow-sm">Your job search, made clearer</div>
        <h1 className="max-w-3xl text-5xl font-extrabold leading-[1.05] text-slate-950 md:text-7xl">Turn one CV into a <span className="gradient-text">smarter application workflow.</span></h1>
        <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-600">Upload your CV, extract your experience automatically, match opportunities, and review polished applications before anything is sent.</p>
        <div className="mt-8 flex flex-wrap gap-3"><Link href="/register" className="rounded-xl bg-indigo-600 px-5 py-3.5 font-bold text-white shadow-xl shadow-indigo-600/20 hover:bg-indigo-700">Build my profile <span aria-hidden>→</span></Link><Link href="#how-it-works" className="rounded-xl border border-slate-300 bg-white/70 px-5 py-3.5 font-bold text-slate-700 hover:border-indigo-300">See how it works</Link></div>
        <div className="mt-8 flex flex-wrap gap-5 text-sm text-slate-500"><span>✓ PDF & DOCX parsing</span><span>✓ Bangla-friendly</span><span>✓ You approve every send</span></div>
      </div>
      <div className="relative"><div className="absolute -inset-8 rounded-[3rem] bg-gradient-to-br from-indigo-200/60 to-cyan-100/60 blur-3xl" /><div className="relative rounded-[2rem] border border-white/80 bg-white/85 p-4 shadow-2xl backdrop-blur md:p-6">
        <div className="mb-4 flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-widest text-indigo-600">Candidate workspace</p><h2 className="mt-1 text-xl font-bold">Profile readiness</h2></div><span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-700">82% ready</span></div>
        <div className="h-3 overflow-hidden rounded-full bg-slate-100"><div className="h-full w-[82%] rounded-full bg-gradient-to-r from-indigo-500 to-cyan-400" /></div>
        <div className="mt-6 grid gap-3 sm:grid-cols-2"><div className="rounded-2xl bg-indigo-50 p-4"><p className="text-2xl font-extrabold text-indigo-700">12</p><p className="mt-1 text-sm text-slate-600">strong matches</p></div><div className="rounded-2xl bg-cyan-50 p-4"><p className="text-2xl font-extrabold text-cyan-700">4</p><p className="mt-1 text-sm text-slate-600">applications to review</p></div></div>
        <div className="mt-4 rounded-2xl border border-slate-200 p-4"><div className="flex items-center justify-between"><div><p className="font-bold">Software Engineer</p><p className="text-sm text-slate-500">Dhaka · Hybrid</p></div><span className="rounded-full bg-emerald-100 px-2 py-1 text-xs font-bold text-emerald-700">92% fit</span></div><div className="mt-4 flex gap-2"><span className="rounded-lg bg-slate-100 px-2 py-1 text-xs">Python</span><span className="rounded-lg bg-slate-100 px-2 py-1 text-xs">React</span><span className="rounded-lg bg-slate-100 px-2 py-1 text-xs">SQL</span></div></div>
      </div></div>
    </section>
    <section id="how-it-works" className="mx-auto max-w-7xl px-5 pb-24 lg:px-8"><div className="mb-8 max-w-xl"><p className="text-sm font-bold uppercase tracking-widest text-indigo-600">How it works</p><h2 className="mt-2 text-3xl font-extrabold">From CV to confident application.</h2></div><div className="grid gap-4 md:grid-cols-3">{[["01","Upload once","Your original PDF or DOCX stays unchanged."],["02","Review facts","Extracted fields fill the gaps while you stay in control."],["03","Apply with clarity","Match jobs and prepare tailored materials grounded in your profile."]].map(([n,t,d]) => <article key={n} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><span className="text-sm font-extrabold text-indigo-600">{n}</span><h3 className="mt-5 text-xl font-bold">{t}</h3><p className="mt-2 leading-7 text-slate-600">{d}</p></article>)}</div></section>
    <footer className="border-t border-slate-200 bg-white/70 px-5 py-8 text-center text-sm text-slate-500">JobApply AI · Prepare better applications, one verified fact at a time.</footer>
  </main></>;
}
