"use client";

import { useRouter } from "next/navigation";
import { useOnboardingStore } from "@/stores/onboarding-store";
import { ProgressHeader } from "@/components/onboarding/progress-header";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MaterialIcon } from "@/components/shared/material-icon";
import type { LearningStyle, ContentDepth, TeachingStyle, AssessmentType, EducationLevel } from "@/types/index";
import { useState } from "react";

const learningStyles: { value: LearningStyle; icon: string; label: string; desc: string }[] = [
  { value: "visual", icon: "visibility", label: "Visual", desc: "Diagrams, maps, and visual storytelling." },
  { value: "depth_first", icon: "layers", label: "Depth-first", desc: "Deep dives into first principles first." },
  { value: "fast_paced", icon: "bolt", label: "Fast-paced", desc: "Concise summaries and rapid testing." },
  { value: "balanced", icon: "balance", label: "Balanced", desc: "A mix of all approaches." },
];

const contentDepths: { value: ContentDepth; label: string; desc: string }[] = [
  { value: "overview", label: "Overview", desc: "High-level understanding" },
  { value: "intermediate", label: "Intermediate", desc: "Solid working knowledge" },
  { value: "deep_dive", label: "Deep Dive", desc: "Expert-level depth" },
];

const teachingStyles: { value: TeachingStyle; label: string; desc: string }[] = [
  { value: "socratic", label: "Socratic", desc: "Questions that guide understanding" },
  { value: "lecture", label: "Lecture", desc: "Structured explanations" },
  { value: "example_based", label: "Example-based", desc: "Learn by real examples" },
  { value: "project_based", label: "Project-based", desc: "Build to learn" },
];

const assessmentTypes: { value: AssessmentType; label: string }[] = [
  { value: "quiz", label: "Quizzes" },
  { value: "project", label: "Projects" },
  { value: "mixed", label: "Mixed" },
  { value: "none", label: "No assessments" },
];

const educationLevels: { value: EducationLevel; label: string }[] = [
  { value: "high_school", label: "High School" },
  { value: "undergraduate", label: "Undergraduate" },
  { value: "graduate", label: "Graduate" },
  { value: "postgraduate", label: "Postgraduate" },
  { value: "professional", label: "Professional" },
  { value: "self_learner", label: "Self Learner" },
];

export default function PreferencesPage() {
  const router = useRouter();
  const { preferences, setPreferences, setCurrentStep } = useOnboardingStore();

  const [style, setStyle] = useState<LearningStyle>(preferences.learningStyle);
  const [depth, setDepth] = useState<ContentDepth>(preferences.contentDepth);
  const [teaching, setTeaching] = useState<TeachingStyle>(preferences.teachingStyle);
  const [assessment, setAssessment] = useState<AssessmentType>(preferences.assessmentType);
  const [education, setEducation] = useState<EducationLevel>(preferences.educationLevel);

  const [styleNote, setStyleNote] = useState(preferences.learningStyleNote);
  const [depthNote, setDepthNote] = useState(preferences.contentDepthNote);
  const [teachingNote, setTeachingNote] = useState(preferences.teachingStyleNote);
  const [assessmentNote, setAssessmentNote] = useState(preferences.assessmentTypeNote);
  const [educationNote, setEducationNote] = useState(preferences.educationLevelNote);

  function handleContinue() {
    setPreferences({
      learningStyle: style,
      contentDepth: depth,
      teachingStyle: teaching,
      assessmentType: assessment,
      educationLevel: education,
      learningStyleNote: styleNote,
      contentDepthNote: depthNote,
      teachingStyleNote: teachingNote,
      assessmentTypeNote: assessmentNote,
      educationLevelNote: educationNote,
    });
    setCurrentStep(2);
    router.push("/onboarding/prerequisites");
  }

  function handleBack() {
    router.push("/onboarding/goal");
  }

  return (
    <>
      <ProgressHeader currentStep={1} />

      <div className="text-center space-y-4">
        <h1 className="text-slate-900 dark:text-slate-100 text-4xl md:text-5xl font-bold tracking-tight leading-tight">
          How do you learn best?
        </h1>
        <p className="text-slate-500 dark:text-slate-400 text-lg">
          Personalize your AI tutor to match your style.
        </p>
      </div>

      <div className="space-y-8">
        {/* Learning Style */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-slate-900 dark:text-slate-100 text-lg font-bold">Learning Style</h3>
            <span className="technical-label text-[10px] uppercase text-slate-400">Personalization Engine</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {learningStyles.map((ls) => (
              <button
                key={ls.value}
                type="button"
                onClick={() => setStyle(ls.value)}
                className={`h-full p-5 flex flex-col gap-3 rounded-xl border text-left transition-all hover:bg-slate-50 dark:hover:bg-slate-800/50 ${
                  style === ls.value
                    ? "border-primary ring-1 ring-primary"
                    : "border-primary/10 bg-white dark:bg-slate-900"
                }`}
              >
                <MaterialIcon name={ls.icon} className="text-primary" />
                <div>
                  <p className="font-bold text-slate-900 dark:text-slate-100">{ls.label}</p>
                  <p className="text-xs text-slate-500 mt-1 leading-relaxed">{ls.desc}</p>
                </div>
              </button>
            ))}
          </div>
          <Textarea
            value={styleNote}
            onChange={(e) => setStyleNote(e.target.value)}
            placeholder="Want to elaborate? Describe your learning style preference in detail..."
            className="mt-3 text-sm resize-none"
            rows={2}
          />
        </div>

        {/* Content Depth */}
        <div className="space-y-4">
          <h3 className="text-slate-900 dark:text-slate-100 text-lg font-bold">Content Depth</h3>
          <div className="grid grid-cols-3 gap-4">
            {contentDepths.map((cd) => (
              <button
                key={cd.value}
                type="button"
                onClick={() => setDepth(cd.value)}
                className={`p-4 rounded-xl border text-left transition-all ${
                  depth === cd.value
                    ? "border-primary ring-1 ring-primary"
                    : "border-primary/10 bg-white dark:bg-slate-900"
                }`}
              >
                <p className="font-bold text-sm">{cd.label}</p>
                <p className="text-xs text-slate-500 mt-1">{cd.desc}</p>
              </button>
            ))}
          </div>
          <Textarea
            value={depthNote}
            onChange={(e) => setDepthNote(e.target.value)}
            placeholder="Want to elaborate? Describe your preferred content depth..."
            className="mt-3 text-sm resize-none"
            rows={2}
          />
        </div>

        {/* Teaching Style */}
        <div className="space-y-4">
          <h3 className="text-slate-900 dark:text-slate-100 text-lg font-bold">Teaching Style</h3>
          <div className="grid grid-cols-2 gap-4">
            {teachingStyles.map((ts) => (
              <button
                key={ts.value}
                type="button"
                onClick={() => setTeaching(ts.value)}
                className={`p-4 rounded-xl border text-left transition-all ${
                  teaching === ts.value
                    ? "border-primary ring-1 ring-primary"
                    : "border-primary/10 bg-white dark:bg-slate-900"
                }`}
              >
                <p className="font-bold text-sm">{ts.label}</p>
                <p className="text-xs text-slate-500 mt-1">{ts.desc}</p>
              </button>
            ))}
          </div>
          <Textarea
            value={teachingNote}
            onChange={(e) => setTeachingNote(e.target.value)}
            placeholder="Want to elaborate? Describe your preferred teaching style..."
            className="mt-3 text-sm resize-none"
            rows={2}
          />
        </div>

        {/* Assessment Type */}
        <div className="space-y-4">
          <h3 className="text-slate-900 dark:text-slate-100 text-lg font-bold">Assessment Preference</h3>
          <div className="grid grid-cols-4 gap-3">
            {assessmentTypes.map((at) => (
              <button
                key={at.value}
                type="button"
                onClick={() => setAssessment(at.value)}
                className={`p-3 rounded-xl border text-center text-sm font-medium transition-all ${
                  assessment === at.value
                    ? "border-primary ring-1 ring-primary text-primary"
                    : "border-primary/10 bg-white dark:bg-slate-900"
                }`}
              >
                {at.label}
              </button>
            ))}
          </div>
          <Textarea
            value={assessmentNote}
            onChange={(e) => setAssessmentNote(e.target.value)}
            placeholder="Want to elaborate? Describe your assessment preference..."
            className="mt-3 text-sm resize-none"
            rows={2}
          />
        </div>

        {/* Education Level */}
        <div className="space-y-4">
          <h3 className="text-slate-900 dark:text-slate-100 text-lg font-bold">Education Level</h3>
          <div className="grid grid-cols-3 gap-3">
            {educationLevels.map((el) => (
              <button
                key={el.value}
                type="button"
                onClick={() => setEducation(el.value)}
                className={`p-3 rounded-xl border text-center text-sm font-medium transition-all ${
                  education === el.value
                    ? "border-primary ring-1 ring-primary text-primary"
                    : "border-primary/10 bg-white dark:bg-slate-900"
                }`}
              >
                {el.label}
              </button>
            ))}
          </div>
          <Textarea
            value={educationNote}
            onChange={(e) => setEducationNote(e.target.value)}
            placeholder="Want to elaborate? Describe your education background..."
            className="mt-3 text-sm resize-none"
            rows={2}
          />
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
