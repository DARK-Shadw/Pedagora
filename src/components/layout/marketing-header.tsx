import Link from "next/link";
import { Logo } from "@/components/shared/logo";
import { Button } from "@/components/ui/button";
import { marketingNav } from "@/config/navigation";

export function MarketingHeader() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-primary/10 bg-[var(--background)]/80 backdrop-blur-md px-6 lg:px-20 py-4 flex items-center justify-between">
      <Link href="/">
        <Logo />
      </Link>

      <nav className="hidden md:flex items-center gap-10">
        {marketingNav.map((item) => (
          <a
            key={item.label}
            href={item.href}
            className="text-charcoal/70 dark:text-slate-400 hover:text-primary text-sm font-medium transition-colors"
          >
            {item.label}
          </a>
        ))}
      </nav>

      <div className="flex items-center gap-3">
        <Button variant="ghost" className="hidden sm:flex" asChild>
          <Link href="/login">Log In</Link>
        </Button>
        <Button asChild>
          <Link href="/signup">Get Started</Link>
        </Button>
      </div>
    </header>
  );
}
