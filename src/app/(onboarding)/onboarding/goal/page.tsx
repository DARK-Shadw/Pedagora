"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { goalSchema, type GoalInput } from "@/lib/validations/onboarding";
import { useOnboardingStore } from "@/stores/onboarding-store";
import { ProgressHeader } from "@/components/onboarding/progress-header";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { MaterialIcon } from "@/components/shared/material-icon";

export default function GoalPage() {
  const router = useRouter();
  const { goal, setGoal, setCurrentStep } = useOnboardingStore();

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<GoalInput>({
    resolver: zodResolver(goalSchema),
    defaultValues: {
      title: goal.title,
      endGoal: goal.endGoal,
      motivation: goal.motivation,
      isExamPrep: goal.isExamPrep,
      examName: goal.examName,
      examDate: goal.examDate,
    },
  });

  const isExamPrep = watch("isExamPrep");

  function onSubmit(data: GoalInput) {
    setGoal({
      title: data.title,
      endGoal: data.endGoal ?? "",
      motivation: data.motivation ?? "",
      isExamPrep: data.isExamPrep,
      examName: data.examName ?? "",
      examDate: data.examDate ?? "",
    });
    setCurrentStep(1);
    router.push("/onboarding/preferences");
  }

  return (
    <>
      <ProgressHeader currentStep={0} />

      <div className="text-center space-y-4">
        <h1 className="text-slate-900 dark:text-slate-100 text-4xl md:text-5xl font-bold tracking-tight leading-tight">
          What do you want to master?
        </h1>
        <p className="text-slate-500 dark:text-slate-400 text-lg">
          Describe your learning goal in a few words.
        </p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-8">
        <div className="w-full">
          <Textarea
            className="min-h-[140px] text-xl p-6 shadow-sm"
            placeholder="e.g. The fundamentals of Quantum Physics, or Building modern web apps with Python..."
            {...register("title")}
          />
          {errors.title && (
            <p className="text-xs text-destructive mt-2">{errors.title.message}</p>
          )}
        </div>

        <div className="space-y-4">
          <Label htmlFor="endGoal" className="text-base font-bold">
            What&apos;s your specific end goal?
          </Label>
          <Input
            id="endGoal"
            placeholder="e.g. Pass the AP Physics exam, Build a SaaS product..."
            {...register("endGoal")}
          />
        </div>

        <div className="space-y-4">
          <Label htmlFor="motivation" className="text-base font-bold">
            What motivates you?
          </Label>
          <Input
            id="motivation"
            placeholder="e.g. Career change, curiosity, academic requirement..."
            {...register("motivation")}
          />
        </div>

        <button
          type="button"
          onClick={() => setValue("isExamPrep", !isExamPrep)}
          className={`w-full flex items-center gap-4 p-5 rounded-xl border text-left transition-all ${
            isExamPrep
              ? "border-primary ring-1 ring-primary"
              : "border-primary/10 bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800/50"
          }`}
        >
          <div className={`flex items-center justify-center w-6 h-6 rounded-md border-2 transition-colors ${
            isExamPrep
              ? "border-primary bg-primary"
              : "border-slate-300 dark:border-slate-600"
          }`}>
            {isExamPrep && (
              <MaterialIcon name="check" className="text-white text-base" />
            )}
          </div>
          <div className="flex-1">
            <p className="font-bold text-sm">Preparing for an exam?</p>
            <p className="text-xs text-slate-500">
              We&apos;ll tailor your schedule to your exam date
            </p>
          </div>
          <MaterialIcon
            name={isExamPrep ? "event_available" : "event"}
            className={`text-2xl ${isExamPrep ? "text-primary" : "text-slate-400"}`}
          />
        </button>

        {isExamPrep && (
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="examName">Exam Name</Label>
              <Input
                id="examName"
                placeholder="e.g. AP Physics"
                {...register("examName")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="examDate">Exam Date</Label>
              <Input
                id="examDate"
                type="date"
                {...register("examDate")}
              />
            </div>
          </div>
        )}

        <div className="flex flex-col gap-4 pt-6 border-t border-primary/5">
          <Button type="submit" size="lg" className="w-full text-lg shadow-lg shadow-primary/20">
            Continue
            <MaterialIcon name="arrow_forward" className="text-xl" />
          </Button>
        </div>
      </form>
    </>
  );
}
