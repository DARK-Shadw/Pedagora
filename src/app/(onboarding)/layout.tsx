import { Logo } from "@/components/shared/logo";

export default function OnboardingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="relative flex min-h-screen w-full flex-col overflow-x-hidden">
      <header className="flex items-center justify-between border-b border-primary/10 px-6 md:px-20 py-4 bg-white/80 dark:bg-[var(--background)]/80 backdrop-blur-md sticky top-0 z-50">
        <a href="/">
          <Logo />
        </a>
        <span className="technical-label text-[10px] uppercase tracking-widest text-slate-500">
          System: Active
        </span>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center px-4 py-12">
        <div className="max-w-[640px] w-full flex flex-col gap-10">
          {children}
        </div>
      </main>

      {/* Decorative gradient */}
      <div className="fixed bottom-0 left-0 w-full h-1/2 pointer-events-none z-[-1] opacity-20 dark:opacity-10">
        <div className="absolute inset-0 bg-gradient-to-t from-primary/20 to-transparent" />
      </div>
    </div>
  );
}
