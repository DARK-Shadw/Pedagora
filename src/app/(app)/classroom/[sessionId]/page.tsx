"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { SessionHeader } from "../components/SessionHeader";
import { PresentationArea } from "../components/PresentationArea";
import { InteractionPanel } from "../components/InteractionPanel";
import { Controls } from "../components/Controls";
import { useTeacherSession } from "../hooks/use-teacher-session";
import { useHeadTTS } from "../hooks/use-headtts";
import { useClassroomStore } from "../stores/classroom-store";
import TalkingHeadAvatar, {
  type TalkingHeadAvatarHandle,
} from "../components/TalkingHeadAvatar";

export default function ClassroomPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(true);
  const [started, setStarted] = useState(false); // User must click Start
  const speechQueueRef = useRef<
    { text: string; segmentId: string }[]
  >([]);
  const isSpeakingRef = useRef(false);

  const {
    status,
    errorMessage,
    sessionSummary,
    teacherSpeech,
  } = useClassroomStore();
  const reset = useClassroomStore((s) => s.reset);
  const setIsSpeaking = useClassroomStore((s) => s.setIsSpeaking);
  const avatarHandleRef = useRef<TalkingHeadAvatarHandle>(null);
  const {
    isLoaded: ttsLoaded,
    isLoading: ttsLoading,
    usesFallback,
    loadProgress,
    initialize: initTTS,
    speak: speakAloud,
    stop: stopTTS,
    setAvatar,
  } = useHeadTTS();

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
    return () => reset();
  }, [router, reset]);

  // Only connect WebSocket AFTER user clicks Start
  const {
    sendResponse,
    sendSpeechDone,
    raiseHand,
    lowerHand,
    sendReaction,
    sendQuestion,
    pauseSession,
    resumeSession,
    leaveSession,
  } = useTeacherSession(started ? sessionId : "", token);

  // Process speech queue one at a time
  const processQueue = () => {
    if (isSpeakingRef.current || speechQueueRef.current.length === 0) return;

    const next = speechQueueRef.current.shift()!;
    isSpeakingRef.current = true;
    setIsSpeaking(true);

    speakAloud(next.text, () => {
      isSpeakingRef.current = false;
      setIsSpeaking(false);
      sendSpeechDone(next.segmentId);
      // Process next in queue
      processQueue();
    });
  };

  // Connect avatar to HeadTTS for lip-synced audio routing
  useEffect(() => {
    if (avatarHandleRef.current && !usesFallback) {
      setAvatar(avatarHandleRef.current);
    }
    return () => setAvatar(null);
  }, [ttsLoaded, usesFallback, setAvatar]);

  // Queue teacher speech (don't play immediately — queue it)
  useEffect(() => {
    if (!teacherSpeech?.text || !started) return;

    speechQueueRef.current.push({
      text: teacherSpeech.text,
      segmentId: teacherSpeech.segmentId,
    });
    processQueue();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [teacherSpeech]);

  const handleStart = async () => {
    // Initialize HeadTTS (requires user gesture for AudioContext)
    await initTTS();
    setStarted(true);
  };

  const handleLeave = () => {
    stopTTS();
    window.speechSynthesis?.cancel();
    leaveSession();
    router.push("/agents");
  };

  if (loading) {
    return (
      <div className="h-screen bg-[#0d1117] flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-[#0d968b] border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-[#8b949e]">Loading classroom...</p>
        </div>
      </div>
    );
  }

  // Start screen — user must click to enable audio
  if (!started) {
    return (
      <div className="h-screen bg-[#0d1117] flex items-center justify-center">
        <div className="flex flex-col items-center gap-6 max-w-md text-center">
          <div className="w-20 h-20 rounded-full bg-[#0d968b]/20 flex items-center justify-center">
            <span
              className="material-symbols-rounded text-4xl text-[#0d968b]"
            >
              school
            </span>
          </div>
          <h1 className="text-white text-2xl font-semibold">
            Ready to Learn?
          </h1>
          <p className="text-[#8b949e] text-sm">
            Your AI teacher Professor Sage is ready. Click below to start the
            lesson. Make sure your speakers are on!
          </p>
          <button
            onClick={handleStart}
            disabled={ttsLoading}
            className="px-8 py-3 bg-[#0d968b] text-white text-lg font-medium rounded-xl hover:bg-[#0b8278] transition-colors shadow-lg shadow-[#0d968b]/20 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {ttsLoading
            ? loadProgress > 0
              ? `Downloading voice model... ${loadProgress}%`
              : "Initializing neural voice..."
            : "Start Lesson"}
          </button>
          {ttsLoading && (
            <div className="w-64">
              <div className="h-1.5 bg-[#21262d] rounded-full overflow-hidden">
                <div
                  className="h-full bg-[#0d968b] rounded-full transition-all duration-300"
                  style={{ width: `${Math.max(loadProgress, 5)}%` }}
                />
              </div>
              <p className="text-xs text-[#8b949e] mt-2">
                {loadProgress > 0
                  ? "Downloading Kokoro neural voice (cached after first use)"
                  : "Connecting to WebGPU..."}
              </p>
            </div>
          )}
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
          <h2 className="text-white text-lg font-medium">Connection Error</h2>
          <p className="text-[#8b949e] text-sm">{errorMessage}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-[#0d968b] text-white text-sm rounded-lg hover:bg-[#0b8278]"
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
            className="w-full mt-6 px-4 py-2.5 bg-[#0d968b] text-white text-sm rounded-lg hover:bg-[#0b8278]"
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
        <div className="flex-1 flex gap-0 min-h-0 p-4">
          {/* Avatar zone */}
          <div className="w-[35%] flex flex-col bg-[#161b22] rounded-lg mr-4 overflow-hidden">
            <div className="flex-1 min-h-0">
              <TalkingHeadAvatar
                ref={avatarHandleRef}
                onStartSpeaking={() => setIsSpeaking(true)}
                onEndSpeaking={() => setIsSpeaking(false)}
              />
            </div>
            <div className="text-center py-2 border-t border-[#30363d]">
              <p className="text-white font-medium text-sm">Professor Sage</p>
              <p className="text-xs text-[#8b949e]">
                {isSpeakingRef.current ? "Speaking..." : status === "active" ? "Listening" : "Paused"}
              </p>
              {usesFallback && (
                <p className="text-xs text-yellow-500/70">Browser voice</p>
              )}
            </div>
          </div>

          {/* Presentation zone */}
          <PresentationArea />
        </div>

        <InteractionPanel
          onSubmitResponse={sendResponse}
          onSubmitQuestion={sendQuestion}
        />

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
