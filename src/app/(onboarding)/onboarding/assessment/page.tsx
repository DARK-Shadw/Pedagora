"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useOnboardingStore } from "@/stores/onboarding-store";
import { ProgressHeader } from "@/components/onboarding/progress-header";
import { Button } from "@/components/ui/button";
import { MaterialIcon } from "@/components/shared/material-icon";
import type { ConfidenceLevel } from "@/types/index";
import type { AssessmentQuestion, AssessmentAnswer } from "@/types/onboarding";

const confidenceLevels: { value: ConfidenceLevel; label: string; color: string }[] = [
  { value: "none", label: "None", color: "text-slate-400" },
  { value: "beginner", label: "Basic", color: "text-amber-500" },
  { value: "intermediate", label: "Comfortable", color: "text-blue-500" },
  { value: "advanced", label: "Strong", color: "text-emerald-500" },
];

export default function AssessmentPage() {
  const router = useRouter();
  const { goal, prerequisites, preferences, assessment, setAssessment, setCurrentStep } =
    useOnboardingStore();

  const [questions, setQuestions] = useState<AssessmentQuestion[]>(assessment.questions);
  const [answers, setAnswers] = useState<Record<string, ConfidenceLevel>>(() => {
    const initial: Record<string, ConfidenceLevel> = {};
    for (const a of assessment.answers) {
      initial[a.questionId] = a.confidence;
    }
    return initial;
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchQuestions = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/assessment/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal: goal.title,
          prerequisites: prerequisites.prerequisites,
          educationLevel: preferences.educationLevel,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Failed to generate questions");
      }

      const data = await res.json();
      setQuestions(data.questions);
      setAnswers({});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }, [goal.title, prerequisites.prerequisites, preferences.educationLevel]);

  useEffect(() => {
    if (questions.length === 0) {
      fetchQuestions();
    }
  }, [questions.length, fetchQuestions]);

  function updateAnswer(questionId: string, confidence: ConfidenceLevel) {
    setAnswers((prev) => ({ ...prev, [questionId]: confidence }));
  }

  function handleContinue() {
    const answerList: AssessmentAnswer[] = questions.map((q) => ({
      questionId: q.id,
      question: q.question,
      confidence: answers[q.id] || "none",
    }));

    setAssessment({ questions, answers: answerList });
    setCurrentStep(5);
    router.push("/onboarding/review");
  }

  function handleBack() {
    // Save current progress before going back
    if (questions.length > 0) {
      const answerList: AssessmentAnswer[] = questions.map((q) => ({
        questionId: q.id,
        question: q.question,
        confidence: answers[q.id] || "none",
      }));
      setAssessment({ questions, answers: answerList });
    }
    router.push("/onboarding/timeline");
  }

  function handleRegenerate() {
    setQuestions([]);
    setAnswers({});
    fetchQuestions();
  }

  const answeredCount = Object.keys(answers).length;
  const totalCount = questions.length;

  return (
    <>
      <ProgressHeader currentStep={4} />

      <div className="text-center space-y-4">
        <h1 className="text-slate-900 dark:text-slate-100 text-4xl md:text-5xl font-bold tracking-tight leading-tight">
          Skill check
        </h1>
        <p className="text-slate-500 dark:text-slate-400 text-lg">
          {goal.title
            ? `Rate your comfort level with these skills related to "${goal.title}".`
            : "Rate your comfort level with these foundational skills."}
        </p>
      </div>

      {loading && (
        <div className="flex flex-col items-center gap-4 py-12">
          <div className="size-10 border-3 border-primary/20 border-t-primary rounded-full animate-spin" />
          <p className="text-slate-500 text-sm">Generating skill assessment questions...</p>
        </div>
      )}

      {error && (
        <div className="flex flex-col items-center gap-4 py-8">
          <div className="flex items-center gap-2 text-sm text-destructive bg-destructive/10 p-3 rounded-lg">
            <MaterialIcon name="error" className="text-lg" />
            {error}
          </div>
          <Button variant="outline" onClick={handleRegenerate}>
            <MaterialIcon name="refresh" className="text-lg" />
            Try again
          </Button>
        </div>
      )}

      {!loading && !error && questions.length > 0 && (
        <>
          <div className="space-y-5">
            {questions.map((q, index) => (
              <div
                key={q.id}
                className="p-5 rounded-xl border border-primary/10 bg-white dark:bg-slate-900 space-y-4"
              >
                <div className="space-y-2">
                  <p className="font-bold text-sm">
                    <span className="text-primary mr-2">{index + 1}.</span>
                    {q.question}
                  </p>
                  {q.context && (
                    <p className="text-xs text-slate-400 italic">{q.context}</p>
                  )}
                </div>

                <div className="grid grid-cols-4 gap-2">
                  {confidenceLevels.map((cl) => (
                    <button
                      key={cl.value}
                      type="button"
                      onClick={() => updateAnswer(q.id, cl.value)}
                      className={`py-2 px-3 rounded-lg text-xs font-medium transition-all text-center ${
                        answers[q.id] === cl.value
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
          </div>

          {totalCount > 0 && (
            <p className="text-center text-sm text-slate-400">
              {answeredCount} of {totalCount} answered
            </p>
          )}
        </>
      )}

      <div className="flex flex-col gap-4 pt-6 border-t border-primary/5">
        <Button
          onClick={handleContinue}
          size="lg"
          className="w-full text-lg shadow-lg shadow-primary/20"
          disabled={loading || questions.length === 0}
        >
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
          {!loading && questions.length > 0 && (
            <button
              onClick={handleRegenerate}
              className="flex-1 py-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors text-sm font-medium"
            >
              Regenerate questions
            </button>
          )}
        </div>
      </div>
    </>
  );
}
