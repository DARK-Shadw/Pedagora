import { MaterialIcon } from "@/components/shared/material-icon";

export function MarketingFooter() {
  return (
    <footer className="bg-white dark:bg-slate-950 border-t border-primary/5 py-12 px-6 lg:px-20">
      <div className="max-w-6xl mx-auto flex flex-col md:flex-row justify-between items-center gap-8">
        <div className="flex items-center gap-2 opacity-50 grayscale">
          <div className="size-6 bg-charcoal dark:bg-slate-300 rounded flex items-center justify-center text-white dark:text-charcoal">
            <MaterialIcon name="architecture" className="text-xs" />
          </div>
          <h2 className="text-charcoal dark:text-white text-lg font-bold tracking-tight">
            Pedagora
          </h2>
        </div>

        <div className="flex gap-8 text-sm text-charcoal/50 dark:text-slate-500">
          <a className="hover:text-primary transition-colors" href="#">
            Twitter
          </a>
          <a className="hover:text-primary transition-colors" href="#">
            LinkedIn
          </a>
          <a className="hover:text-primary transition-colors" href="#">
            Privacy Policy
          </a>
          <a className="hover:text-primary transition-colors" href="#">
            Terms of Service
          </a>
        </div>

        <p className="text-xs text-charcoal/30 dark:text-slate-600">
          &copy; {new Date().getFullYear()} Pedagora AI. All rights reserved.
        </p>
      </div>
    </footer>
  );
}
