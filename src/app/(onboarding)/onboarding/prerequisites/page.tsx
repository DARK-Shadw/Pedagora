"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useOnboardingStore } from "@/stores/onboarding-store";
import { ProgressHeader } from "@/components/onboarding/progress-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MaterialIcon } from "@/components/shared/material-icon";
import type { ConfidenceLevel } from "@/types/index";
import type { PrerequisiteItem } from "@/types/onboarding";

const confidenceLevels: { value: ConfidenceLevel; label: string; color: string }[] = [
  { value: "none", label: "No experience", color: "text-slate-400" },
  { value: "beginner", label: "Beginner", color: "text-amber-500" },
  { value: "intermediate", label: "Intermediate", color: "text-blue-500" },
  { value: "advanced", label: "Advanced", color: "text-emerald-500" },
];

export default function PrerequisitesPage() {
  const router = useRouter();
  const { prerequisites, setPrerequisites, setCurrentStep, goal } =
    useOnboardingStore();

  const [skills, setSkills] = useState<PrerequisiteItem[]>(
    prerequisites.prerequisites.length > 0
      ? prerequisites.prerequisites
      : [{ skillName: "", confidenceLevel: "none", notes: "" }]
  );
  const [newSkill, setNewSkill] = useState("");

  function addSkill() {
    if (newSkill.trim()) {
      setSkills([...skills, { skillName: newSkill.trim(), confidenceLevel: "none", notes: "" }]);
      setNewSkill("");
    }
  }

  function removeSkill(index: number) {
    setSkills(skills.filter((_, i) => i !== index));
  }

  function updateConfidence(index: number, level: ConfidenceLevel) {
    const updated = [...skills];
    updated[index] = { ...updated[index], confidenceLevel: level };
    setSkills(updated);
  }

  function handleContinue() {
    setPrerequisites({
      prerequisites: skills.filter((s) => s.skillName.trim() !== ""),
    });
    setCurrentStep(3);
    router.push("/onboarding/timeline");
  }

  function handleBack() {
    router.push("/onboarding/preferences");
  }

  function handleSkip() {
    setPrerequisites({ prerequisites: [] });
    setCurrentStep(3);
    router.push("/onboarding/timeline");
  }

  return (
    <>
      <ProgressHeader currentStep={2} />

      <div className="text-center space-y-4">
        <h1 className="text-slate-900 dark:text-slate-100 text-4xl md:text-5xl font-bold tracking-tight leading-tight">
          What do you already know?
        </h1>
        <p className="text-slate-500 dark:text-slate-400 text-lg">
          {goal.title
            ? `Rate your current skills related to "${goal.title}".`
            : "Rate your current knowledge on related topics."}
        </p>
      </div>

      <div className="space-y-6">
        {/* Existing skills */}
        {skills.map((skill, index) => (
          <div
            key={index}
            className="p-5 rounded-xl border border-primary/10 bg-white dark:bg-slate-900 space-y-4"
          >
            <div className="flex items-center justify-between">
              {skill.skillName ? (
                <p className="font-bold text-sm">{skill.skillName}</p>
              ) : (
                <Input
                  placeholder="e.g. Linear Algebra, Python basics..."
                  value={skill.skillName}
                  onChange={(e) => {
                    const updated = [...skills];
                    updated[index] = { ...updated[index], skillName: e.target.value };
                    setSkills(updated);
                  }}
                  className="border-0 p-0 h-auto font-bold text-sm focus-visible:ring-0"
                />
              )}
              <button
                type="button"
                onClick={() => removeSkill(index)}
                className="text-slate-400 hover:text-destructive transition-colors"
              >
                <MaterialIcon name="close" className="text-lg" />
              </button>
            </div>

            <div className="grid grid-cols-4 gap-2">
              {confidenceLevels.map((cl) => (
                <button
                  key={cl.value}
                  type="button"
                  onClick={() => updateConfidence(index, cl.value)}
                  className={`py-2 px-3 rounded-lg text-xs font-medium transition-all text-center ${
                    skill.confidenceLevel === cl.value
                      ? "border-primary ring-1 ring-primary bg-primary/5 text-primary"
                      : "border border-primary/10 bg-slate-50 dark:bg-slate-800"
                  }`}
                >
                  {cl.label}
                </button>
              ))}
            </div>
          </div>
        ))}

        {/* Add new skill */}
        <div className="flex gap-3">
          <Input
            placeholder="Add a skill or topic..."
            value={newSkill}
            onChange={(e) => setNewSkill(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addSkill())}
          />
          <Button variant="outline" onClick={addSkill} type="button">
            <MaterialIcon name="add" />
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-4 pt-6 border-t border-primary/5">
        <Button onClick={handleContinue} size="lg" className="w-full text-lg shadow-lg shadow-primary/20">
          Continue
          <MaterialIcon name="arrow_forward" className="text-xl" />
        </Button>
        <div className="flex gap-4">
          <button
            onClick={handleBack}
            className="flex-1 py-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors text-sm font-medium"
          >
            Back
          </button>
          <button
            onClick={handleSkip}
            className="flex-1 py-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors text-sm font-medium"
          >
            Skip for now
          </button>
        </div>
      </div>
    </>
  );
}
