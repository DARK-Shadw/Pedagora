"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useOnboardingStore } from "@/stores/onboarding-store";
import { getAllPendingFiles, clearPendingFiles } from "@/stores/pending-files";
import { ProgressHeader } from "@/components/onboarding/progress-header";
import { Button } from "@/components/ui/button";
import { MaterialIcon } from "@/components/shared/material-icon";
import { createClient } from "@/lib/supabase/client";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ReviewPage() {
  const router = useRouter();
  const { goal, preferences, prerequisites, timeline, assessment, resources, reset } =
    useOnboardingStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLaunch() {
    setLoading(true);
    setError(null);

    try {
      const supabase = createClient();
      const {
        data: { user },
      } = await supabase.auth.getUser();

      if (!user) {
        router.push("/login");
        return;
      }

      // 1. Update profile — only set "in_progress" for first-time users
      const { data: profile } = await supabase
        .from("profiles")
        .select("onboarding_status")
        .eq("id", user.id)
        .single();

      const isFirstTime = profile?.onboarding_status !== "completed";

      if (isFirstTime) {
        await supabase
          .from("profiles")
          .update({
            onboarding_status: "in_progress",
            education_level: preferences.educationLevel,
          })
          .eq("id", user.id);
      } else {
        await supabase
          .from("profiles")
          .update({ education_level: preferences.educationLevel })
          .eq("id", user.id);
      }

      // 2. Insert learning goal
      const { data: goalData, error: goalError } = await supabase
        .from("learning_goals")
        .insert({
          user_id: user.id,
          title: goal.title,
          end_goal: goal.endGoal || null,
          motivation: goal.motivation || null,
          is_exam_prep: goal.isExamPrep,
          exam_name: goal.examName || null,
          exam_date: goal.examDate || null,
        })
        .select()
        .single();

      if (goalError) throw goalError;

      // 3. Insert user preferences
      await supabase.from("user_preferences").upsert({
        user_id: user.id,
        learning_style: preferences.learningStyle,
        content_depth: preferences.contentDepth,
        teaching_style: preferences.teachingStyle,
        assessment_type: preferences.assessmentType,
        learning_style_note: preferences.learningStyleNote,
        content_depth_note: preferences.contentDepthNote,
        teaching_style_note: preferences.teachingStyleNote,
        assessment_type_note: preferences.assessmentTypeNote,
        education_level_note: preferences.educationLevelNote,
        session_frequency: timeline.sessionFrequency,
        session_duration_minutes: timeline.sessionDurationMinutes,
        hours_per_week: timeline.hoursPerWeek,
      });

      // 4. Insert prerequisites
      if (prerequisites.prerequisites.length > 0) {
        await supabase.from("prerequisites").insert(
          prerequisites.prerequisites
            .filter((p) => p.skillName.trim())
            .map((p) => ({
              goal_id: goalData.id,
              user_id: user.id,
              skill_name: p.skillName,
              confidence_level: p.confidenceLevel,
              notes: p.notes || null,
            }))
        );
      }

      // 5. Insert skill assessments
      if (assessment.answers.length > 0) {
        await supabase.from("skill_assessments").insert(
          assessment.answers.map((a) => ({
            goal_id: goalData.id,
            user_id: user.id,
            question: a.question,
            context: "",
            confidence_level: a.confidence,
          }))
        );
      }

      // 6. Create initial agent tasks
      const isEpisode = goal.contentType === "single_episode";
      const agentTypes = isEpisode
        ? (["planning", "visualization", "teaching"] as const)
        : (["research", "planning", "visualization", "teaching"] as const);
      await supabase.from("agent_tasks").insert(
        agentTypes.map((type) => ({
          goal_id: goalData.id,
          user_id: user.id,
          agent_type: type,
          status: "queued",
        }))
      );

      // 6.5. Upload resource files to Supabase Storage + insert user_resources records
      const pendingFiles = getAllPendingFiles();
      if (resources.files.length > 0 && pendingFiles.size > 0) {
        for (const fileInfo of resources.files) {
          const file = pendingFiles.get(fileInfo.id);
          if (!file) continue;

          const storagePath = `${user.id}/${goalData.id}/${fileInfo.id}_${fileInfo.fileName}`;

          // Upload to Supabase Storage
          const { error: uploadError } = await supabase.storage
            .from("user-resources")
            .upload(storagePath, file);

          if (uploadError) {
            console.error(`Failed to upload ${fileInfo.fileName}:`, uploadError);
            continue;
          }

          // Insert user_resources record
          await supabase.from("user_resources").insert({
            id: fileInfo.id,
            goal_id: goalData.id,
            user_id: user.id,
            file_name: fileInfo.fileName,
            file_type: fileInfo.fileType,
            file_size_bytes: fileInfo.fileSizeBytes,
            storage_path: storagePath,
            status: "uploaded",
          });
        }

        clearPendingFiles();
      }

      // 7. Trigger the appropriate pipeline (fire-and-forget)
      const { data: sessionData } = await supabase.auth.getSession();
      if (sessionData.session?.access_token) {
        const headers = {
          "Content-Type": "application/json",
          Authorization: `Bearer ${sessionData.session.access_token}`,
        };
        const body = JSON.stringify({ goal_id: goalData.id });

        if (isEpisode) {
          fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/agents/plan-episode`, {
            method: "POST",
            headers,
            body,
          }).catch(() => {});
        } else {
          fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/agents/research`, {
            method: "POST",
            headers,
            body,
          }).catch(() => {});

          if (resources.files.length > 0) {
            fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/resources/process`, {
              method: "POST",
              headers,
              body,
            }).catch(() => {});
          }
        }
      }

      // 8. Mark onboarding as completed
      await supabase
        .from("profiles")
        .update({ onboarding_status: "completed" })
        .eq("id", user.id);

      // 9. Clear onboarding store and redirect
      reset();
      router.push("/agents");
      router.refresh();
    } catch (err) {
      console.error("Onboarding error:", err);
      setError("Something went wrong. Please try again.");
      setLoading(false);
    }
  }

  return (
    <>
      <ProgressHeader currentStep={6} />

      <div className="text-center space-y-4">
        <h1 className="text-slate-900 dark:text-slate-100 text-4xl md:text-5xl font-bold tracking-tight leading-tight">
          Review your plan
        </h1>
        <p className="text-slate-500 dark:text-slate-400 text-lg">
          {goal.contentType === "single_episode"
            ? "Everything looks good? Generate your episode with Gemini."
            : "Everything looks good? Launch your AI agents to build your curriculum."}
        </p>
      </div>

      <div className="space-y-6">
        {/* Goal Summary */}
        <ReviewSection
          title="Learning Goal"
          icon="school"
          editHref="/onboarding/goal"
        >
          <div className="flex items-center gap-2 mb-2">
            <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold ${
              goal.contentType === "single_episode"
                ? "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300"
                : "bg-primary/10 text-primary"
            }`}>
              <MaterialIcon
                name={goal.contentType === "single_episode" ? "play_circle" : "library_books"}
                className="text-sm"
              />
              {goal.contentType === "single_episode" ? "Single Episode" : "Full Course"}
            </span>
          </div>
          <p className="text-lg font-bold">{goal.title || "Not set"}</p>
          {goal.endGoal && (
            <p className="text-sm text-slate-500 mt-1">Goal: {goal.endGoal}</p>
          )}
          {goal.motivation && (
            <p className="text-sm text-slate-500">Motivation: {goal.motivation}</p>
          )}
          {goal.isExamPrep && (
            <p className="text-sm text-primary mt-1">
              Exam prep: {goal.examName} {goal.examDate && `on ${goal.examDate}`}
            </p>
          )}
        </ReviewSection>

        {/* Preferences Summary */}
        <ReviewSection
          title="Learning Preferences"
          icon="tune"
          editHref="/onboarding/preferences"
        >
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-slate-500">Style</p>
              <p className="font-medium capitalize">{preferences.learningStyle.replace("_", " ")}</p>
              {preferences.learningStyleNote && (
                <p className="text-xs text-slate-400 mt-1 italic">&ldquo;{preferences.learningStyleNote}&rdquo;</p>
              )}
            </div>
            <div>
              <p className="text-slate-500">Depth</p>
              <p className="font-medium capitalize">{preferences.contentDepth.replace("_", " ")}</p>
              {preferences.contentDepthNote && (
                <p className="text-xs text-slate-400 mt-1 italic">&ldquo;{preferences.contentDepthNote}&rdquo;</p>
              )}
            </div>
            <div>
              <p className="text-slate-500">Teaching</p>
              <p className="font-medium capitalize">{preferences.teachingStyle.replace("_", " ")}</p>
              {preferences.teachingStyleNote && (
                <p className="text-xs text-slate-400 mt-1 italic">&ldquo;{preferences.teachingStyleNote}&rdquo;</p>
              )}
            </div>
            <div>
              <p className="text-slate-500">Assessment</p>
              <p className="font-medium capitalize">{preferences.assessmentType}</p>
              {preferences.assessmentTypeNote && (
                <p className="text-xs text-slate-400 mt-1 italic">&ldquo;{preferences.assessmentTypeNote}&rdquo;</p>
              )}
            </div>
          </div>
          {preferences.educationLevelNote && (
            <div className="mt-3 text-sm">
              <p className="text-slate-500">Education note</p>
              <p className="text-xs text-slate-400 mt-1 italic">&ldquo;{preferences.educationLevelNote}&rdquo;</p>
            </div>
          )}
        </ReviewSection>

        {/* Prerequisites Summary */}
        <ReviewSection
          title="Prerequisites"
          icon="checklist"
          editHref="/onboarding/prerequisites"
        >
          {prerequisites.prerequisites.length > 0 ? (
            <div className="space-y-2">
              {prerequisites.prerequisites.map((p, i) => (
                <div key={i} className="flex items-center justify-between text-sm">
                  <span>{p.skillName}</span>
                  <span className="capitalize text-slate-500">
                    {p.confidenceLevel.replace("_", " ")}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">No prerequisites added</p>
          )}
        </ReviewSection>

        {/* Assessment Summary */}
        {assessment.answers.length > 0 && (
          <ReviewSection
            title="Skill Assessment"
            icon="quiz"
            editHref="/onboarding/assessment"
          >
            <div className="space-y-2">
              {assessment.answers.map((a) => (
                <div key={a.questionId} className="flex items-center justify-between text-sm">
                  <span className="flex-1 mr-4">{a.question}</span>
                  <span className="capitalize text-slate-500 shrink-0">
                    {a.confidence}
                  </span>
                </div>
              ))}
            </div>
          </ReviewSection>
        )}

        {/* Timeline Summary */}
        <ReviewSection
          title="Schedule"
          icon="schedule"
          editHref="/onboarding/timeline"
        >
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-slate-500">Hours/week</p>
              <p className="font-medium">{timeline.hoursPerWeek}h</p>
            </div>
            <div>
              <p className="text-slate-500">Frequency</p>
              <p className="font-medium capitalize">
                {timeline.sessionFrequency.replace(/_/g, " ")}
              </p>
            </div>
            <div>
              <p className="text-slate-500">Session length</p>
              <p className="font-medium">{timeline.sessionDurationMinutes} min</p>
            </div>
            {timeline.targetDate && (
              <div>
                <p className="text-slate-500">Target date</p>
                <p className="font-medium">{timeline.targetDate}</p>
              </div>
            )}
          </div>
        </ReviewSection>

        {/* Resources Summary */}
        <ReviewSection
          title="Study Materials"
          icon="folder_open"
          editHref="/onboarding/resources"
        >
          {resources.files.length > 0 ? (
            <div className="space-y-2">
              {resources.files.map((f) => (
                <div key={f.id} className="flex items-center justify-between text-sm">
                  <span className="truncate flex-1 mr-4">{f.fileName}</span>
                  <span className="text-slate-500 shrink-0">
                    {f.fileType.toUpperCase()} &middot; {formatFileSize(f.fileSizeBytes)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">No materials uploaded</p>
          )}
        </ReviewSection>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-destructive bg-destructive/10 p-3 rounded-lg">
          <MaterialIcon name="error" className="text-lg" />
          {error}
        </div>
      )}

      <div className="flex flex-col gap-4 pt-6 border-t border-primary/5">
        <Button
          onClick={handleLaunch}
          size="lg"
          className="w-full text-lg shadow-lg shadow-primary/20"
          disabled={loading}
        >
          {loading ? (
            goal.contentType === "single_episode" ? "Generating episode..." : "Launching agents..."
          ) : (
            <>
              {goal.contentType === "single_episode" ? "Generate Episode" : "Launch AI Agents"}
              <MaterialIcon name={goal.contentType === "single_episode" ? "play_circle" : "rocket_launch"} className="text-xl" />
            </>
          )}
        </Button>
        <button
          onClick={() => router.push("/onboarding/resources")}
          className="w-full py-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors text-sm font-medium"
        >
          Back to previous step
        </button>
      </div>
    </>
  );
}

function ReviewSection({
  title,
  icon,
  editHref,
  children,
}: {
  title: string;
  icon: string;
  editHref: string;
  children: React.ReactNode;
}) {
  return (
    <div className="p-6 rounded-xl border border-primary/10 bg-white dark:bg-slate-900">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <MaterialIcon name={icon} className="text-primary" />
          <h3 className="font-bold">{title}</h3>
        </div>
        <a
          href={editHref}
          className="text-xs text-primary font-bold hover:underline"
        >
          Edit
        </a>
      </div>
      {children}
    </div>
  );
}
