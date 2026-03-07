"use client";

import { onboardingSteps } from "@/config/onboarding-steps";

interface ProgressHeaderProps {
  currentStep: number;
}

export function ProgressHeader({ currentStep }: ProgressHeaderProps) {
  const step = onboardingSteps[currentStep];
  const progress = ((currentStep + 1) / onboardingSteps.length) * 100;

  return (
    <div className="flex flex-col gap-4 w-full">
      <div className="flex justify-between items-end">
        <div className="flex flex-col">
          <span className="technical-label text-[10px] uppercase tracking-widest text-primary font-bold">
            Step {String(currentStep + 1).padStart(2, "0")}
          </span>
          <p className="text-slate-900 dark:text-slate-100 text-sm font-medium">
            {step?.title ?? "Onboarding"}
          </p>
        </div>
        <p className="technical-label text-xs text-slate-500">
          {Math.round(progress)}% Complete
        </p>
      </div>
      <div className="h-1.5 w-full rounded-full bg-primary/10 overflow-hidden">
        <div
          className="h-full rounded-full bg-primary transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}
