"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { SessionHeader } from "../components/SessionHeader";
import { PresentationArea } from "../components/PresentationArea";
import { InteractionPanel } from "../components/InteractionPanel";
import { Controls } from "../components/Controls";
import { useTeacherSession } from "../hooks/use-teacher-session";
import { useSpeechSynthesis } from "../hooks/use-speech";
import { useClassroomStore } from "../stores/classroom-store";

export default function ClassroomPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(true);

  const { status, errorMessage, sessionSummary, teacherSpeech } =
    useClassroomStore();
  const reset = useClassroomStore((s) => s.reset);
  const setIsSpeaking = useClassroomStore((s) => s.setIsSpeaking);
  const { speak: speakAloud, isSpeaking: ttsActive } = useSpeechSynthesis();

  // Speak teacher speech aloud via browser TTS
  useEffect(() => {
    if (teacherSpeech?.text) {
      speakAloud(teacherSpeech.text, 0.95);
      setIsSpeaking(true);
    }
  }, [teacherSpeech, speakAloud, setIsSpeaking]);

  useEffect(() => {
    if (!ttsActive) {
      setIsSpeaking(false);
    }
  }, [ttsActive, setIsSpeaking]);

  // Get auth token
  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getSession().then(({ data }) => {
      if (data.session?.access_token) {
        setToken(data.session.access_token);
        setLoading(false);
      } else {
        router.push("/login");
      }
    });

    return () => {
      reset();
    };
  }, [router, reset]);

  // WebSocket connection
  const {
    sendResponse,
    raiseHand,
    lowerHand,
    sendReaction,
    sendQuestion,
    pauseSession,
    resumeSession,
    leaveSession,
  } = useTeacherSession(sessionId, token);

  const handleLeave = () => {
    leaveSession();
    router.push("/agents");
  };

  if (loading) {
    return (
      <div className="h-screen bg-[#0d1117] flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-[#0d968b] border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-[#8b949e]">Joining classroom...</p>
        </div>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="h-screen bg-[#0d1117] flex items-center justify-center">
        <div className="flex flex-col items-center gap-4 max-w-md text-center">
          <span className="material-symbols-rounded text-red-500 text-5xl">
            error
          </span>
          <h2 className="text-white text-lg font-medium">
            Connection Error
          </h2>
          <p className="text-[#8b949e] text-sm">{errorMessage}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-[#0d968b] text-white text-sm rounded-lg hover:bg-[#0b8278] transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (status === "completed" && sessionSummary) {
    return (
      <div className="h-screen bg-[#0d1117] flex items-center justify-center">
        <div className="bg-[#161b22] border border-[#30363d] rounded-xl p-8 max-w-lg w-full">
          <div className="flex items-center gap-3 mb-6">
            <span className="material-symbols-rounded text-[#0d968b] text-3xl">
              celebration
            </span>
            <h2 className="text-white text-xl font-medium">
              Lesson Complete!
            </h2>
          </div>

          <div className="space-y-4">
            {sessionSummary.time_spent_minutes != null && (
              <div className="flex justify-between text-sm">
                <span className="text-[#8b949e]">Time spent</span>
                <span className="text-white">
                  {String(sessionSummary.time_spent_minutes)} min
                </span>
              </div>
            )}
            {sessionSummary.segments_completed != null && (
              <div className="flex justify-between text-sm">
                <span className="text-[#8b949e]">Segments completed</span>
                <span className="text-white">
                  {String(sessionSummary.segments_completed)}
                </span>
              </div>
            )}
            {sessionSummary.questions_asked != null && (
              <div className="flex justify-between text-sm">
                <span className="text-[#8b949e]">Questions</span>
                <span className="text-white">
                  {String(sessionSummary.questions_correct)}/
                  {String(sessionSummary.questions_asked)} correct
                </span>
              </div>
            )}

            {(sessionSummary.areas_for_review as string[])?.length > 0 && (
              <div>
                <p className="text-sm text-[#8b949e] mb-2">
                  Areas to review:
                </p>
                <ul className="space-y-1">
                  {(sessionSummary.areas_for_review as string[]).map(
                    (area, i) => (
                      <li
                        key={i}
                        className="text-xs text-yellow-400 bg-yellow-500/10 px-3 py-1.5 rounded"
                      >
                        {area}
                      </li>
                    )
                  )}
                </ul>
              </div>
            )}
          </div>

          <button
            onClick={() => router.push("/agents")}
            className="w-full mt-6 px-4 py-2.5 bg-[#0d968b] text-white text-sm rounded-lg hover:bg-[#0b8278] transition-colors"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-[#0d1117]">
      <SessionHeader />

      <div className="flex-1 flex flex-col min-h-0">
        {/* Main content area */}
        <div className="flex-1 flex gap-0 min-h-0 p-4">
          {/* Avatar zone (left ~35%) */}
          <div className="w-[35%] flex flex-col items-center justify-center bg-[#161b22] rounded-lg mr-4">
            {/* Avatar placeholder — will be replaced with TalkingHead.js */}
            <div className="flex flex-col items-center gap-4">
              <div className="w-32 h-32 rounded-full bg-[#21262d] flex items-center justify-center">
                <span className="material-symbols-rounded text-6xl text-[#0d968b]">
                  record_voice_over
                </span>
              </div>
              <div className="text-center">
                <p className="text-white font-medium">Professor Sage</p>
                <p className="text-xs text-[#8b949e]">
                  {status === "active"
                    ? "Teaching..."
                    : status === "paused"
                    ? "Paused"
                    : "Connecting..."}
                </p>
              </div>
            </div>
          </div>

          {/* Presentation zone (right ~65%) */}
          <PresentationArea />
        </div>

        {/* Interaction panel */}
        <InteractionPanel
          onSubmitResponse={sendResponse}
          onSubmitQuestion={sendQuestion}
        />

        {/* Controls bar */}
        <Controls
          onRaiseHand={raiseHand}
          onLowerHand={lowerHand}
          onReaction={sendReaction}
          onPause={pauseSession}
          onResume={resumeSession}
          onLeave={handleLeave}
        />
      </div>
    </div>
  );
}
