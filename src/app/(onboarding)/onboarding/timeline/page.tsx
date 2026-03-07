"use client";

import { useRouter } from "next/navigation";
import { useOnboardingStore } from "@/stores/onboarding-store";
import { ProgressHeader } from "@/components/onboarding/progress-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { MaterialIcon } from "@/components/shared/material-icon";
import type { SessionFrequency } from "@/types/index";
import { useState } from "react";

const frequencies: { value: SessionFrequency; label: string; desc: string }[] = [
  { value: "daily", label: "Daily", desc: "Every day" },
  { value: "every_other_day", label: "Every other day", desc: "3-4x/week" },
  { value: "three_per_week", label: "3x/week", desc: "Mon/Wed/Fri" },
  { value: "weekly", label: "Weekly", desc: "Once a week" },
];

const durations = [15, 30, 45, 60, 90, 120];

export default function TimelinePage() {
  const router = useRouter();
  const { timeline, setTimeline, setCurrentStep } = useOnboardingStore();

  const [targetDate, setTargetDate] = useState(timeline.targetDate);
  const [hoursPerWeek, setHoursPerWeek] = useState(timeline.hoursPerWeek);
  const [frequency, setFrequency] = useState<SessionFrequency>(timeline.sessionFrequency);
  const [duration, setDuration] = useState(timeline.sessionDurationMinutes);

  function handleContinue() {
    setTimeline({
      targetDate,
      hoursPerWeek,
      sessionFrequency: frequency,
      sessionDurationMinutes: duration,
    });
    setCurrentStep(4);
    router.push("/onboarding/assessment");
  }

  function handleBack() {
    router.push("/onboarding/prerequisites");
  }

  return (
    <>
      <ProgressHeader currentStep={3} />

      <div className="text-center space-y-4">
        <h1 className="text-slate-900 dark:text-slate-100 text-4xl md:text-5xl font-bold tracking-tight leading-tight">
          Set your schedule
        </h1>
        <p className="text-slate-500 dark:text-slate-400 text-lg">
          When and how often do you want to learn?
        </p>
      </div>

      <div className="space-y-8">
        {/* Target Date */}
        <div className="space-y-3">
          <Label className="text-base font-bold">Target completion date (optional)</Label>
          <Input
            type="date"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
          />
        </div>

        {/* Hours per week */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <Label className="text-base font-bold">Hours per week</Label>
            <span className="technical-label text-sm font-bold text-primary">{hoursPerWeek}h</span>
          </div>
          <Slider
            value={[hoursPerWeek]}
            onValueChange={([v]) => setHoursPerWeek(v)}
            min={1}
            max={20}
            step={1}
          />
          <div className="flex justify-between text-xs text-slate-400">
            <span>1 hour</span>
            <span>20 hours</span>
          </div>
        </div>

        {/* Session Frequency */}
        <div className="space-y-4">
          <Label className="text-base font-bold">Session frequency</Label>
          <div className="grid grid-cols-2 gap-4">
            {frequencies.map((f) => (
              <button
                key={f.value}
                type="button"
                onClick={() => setFrequency(f.value)}
                className={`p-4 rounded-xl border text-left transition-all ${
                  frequency === f.value
                    ? "border-primary ring-1 ring-primary"
                    : "border-primary/10 bg-white dark:bg-slate-900"
                }`}
              >
                <p className="font-bold text-sm">{f.label}</p>
                <p className="text-xs text-slate-500 mt-1">{f.desc}</p>
              </button>
            ))}
          </div>
        </div>

        {/* Session Duration */}
        <div className="space-y-4">
          <Label className="text-base font-bold">Session duration</Label>
          <div className="grid grid-cols-3 gap-3">
            {durations.map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDuration(d)}
                className={`p-3 rounded-xl border text-center text-sm font-medium transition-all ${
                  duration === d
                    ? "border-primary ring-1 ring-primary text-primary"
                    : "border-primary/10 bg-white dark:bg-slate-900"
                }`}
              >
                {d} min
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-4 pt-6 border-t border-primary/5">
        <Button onClick={handleContinue} size="lg" className="w-full text-lg shadow-lg shadow-primary/20">
          Continue
          <MaterialIcon name="arrow_forward" className="text-xl" />
        </Button>
        <button
          onClick={handleBack}
          className="w-full py-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors text-sm font-medium"
        >
          Back to previous step
        </button>
      </div>
    </>
  );
}
