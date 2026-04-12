"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { useClassroomStore, type DialogueEntry } from "../stores/classroom-store";
import { AnimationFrame, useAnimationCommands } from "../components/AnimationFrame";
import { AvatarPiP, type AvatarPiPHandle } from "../components/AvatarPiP";
import { SubtitleOverlay } from "../components/SubtitleOverlay";
import { TopBar } from "../components/TopBar";
import { ControlBar } from "../components/ControlBar";
import { QuestionOverlay } from "../components/QuestionOverlay";
import { ChatPanel } from "../components/ChatPanel";
import { StartScreen } from "../components/StartScreen";
import { LockstepEngine, type FrameBundle } from "../lib/lockstep-engine";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export default function ClassroomV2Page() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;

  // Auth
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(true);
  const [started, setStarted] = useState(false);
  const [hasFirstFrame, setHasFirstFrame] = useState(false);
  const [canResume, setCanResume] = useState(false);
  const freshStartRef = useRef(false);

  // Refs
  const wsRef = useRef<WebSocket | null>(null);
  const avatarRef = useRef<AvatarPiPHandle>(null);
  const reconnectAttempts = useRef(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const currentSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const engineRef = useRef<LockstepEngine | null>(null);

  // Store
  const store = useClassroomStore();
  const {
    status, lessonTitle, currentFrame, currentQuestion,
    teacherSpeech, isSpeaking, isHandRaised, isChatOpen, isMicOn,
    messages, elapsedSeconds, summary, frameTitle, fallbackDescription,
  } = store;

  // Animation commands (postMessage to iframe) — kept for legacy speak/seek_step messages
  const { seekToStep, play: playAnim, pause: pauseAnim } = useAnimationCommands();

  // ── WebSocket send helpers ──
  const sendSpeechDone = useCallback(() => {
    console.log("[SYNC] speech_done -> backend");
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "speech_done" }));
    }
  }, []);

  const sendFrameDone = useCallback(() => {
    console.log("[SYNC] frame_done -> backend");
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "frame_done" }));
    }
  }, []);

  // ── Legacy single-shot audio (used for opening / closing / feedback messages) ──
  const playAudio = useCallback(async (base64Wav: string, text: string, speechType: string) => {
    if (!audioCtxRef.current || audioCtxRef.current.state === "closed") {
      audioCtxRef.current = new AudioContext();
    }
    const ctx = audioCtxRef.current;
    if (ctx.state === "suspended") await ctx.resume();

    try {
      const binaryStr = atob(base64Wav);
      const bytes = new Uint8Array(binaryStr.length);
      for (let i = 0; i < binaryStr.length; i++) bytes[i] = binaryStr.charCodeAt(i);
      const audioBuffer = await ctx.decodeAudioData(bytes.buffer);

      store.setTeacherSpeech(text, speechType);
      store.setIsSpeaking(true);

      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);
      currentSourceRef.current = source;

      source.onended = () => {
        console.log(`[AUDIO] Finished (${audioBuffer.duration.toFixed(1)}s)`);
        store.setIsSpeaking(false);
        store.clearTeacherSpeech();
        currentSourceRef.current = null;
        sendSpeechDone();
      };

      console.log(`[AUDIO] Playing ${audioBuffer.duration.toFixed(1)}s`);
      source.start();
    } catch (e) {
      console.error("[AUDIO] decode/play failed:", e);
      // Auto-fire speech_done so backend doesn't hang
      sendSpeechDone();
    }
  }, [store, sendSpeechDone]);

  const stopAudio = useCallback(() => {
    try {
      currentSourceRef.current?.stop();
      currentSourceRef.current = null;
    } catch { /* already stopped */ }
    engineRef.current?.stop();
    store.setIsSpeaking(false);
    store.clearTeacherSpeech();
  }, [store]);

  // ── Auth: get Supabase token + check if session is resumable ──
  useEffect(() => {
    let cancelled = false;
    async function init() {
      const supabase = createClient();
      const { data } = await supabase.auth.getSession();
      const t = data.session?.access_token || "";
      if (cancelled) return;
      setToken(t);

      // Check if session has prior progress (frames_completed)
      if (t && sessionId) {
        try {
          const res = await fetch(`${BACKEND_URL}/teacher/sessions/${sessionId}`, {
            headers: { Authorization: `Bearer ${t}` },
          });
          if (res.ok) {
            const session = await res.json();
            const completed: string[] =
              session?.dialogue_state?.frames_completed ?? [];
            if (!cancelled && completed.length > 0) {
              setCanResume(true);
            }
          }
        } catch (e) {
          console.warn("[Classroom] session lookup failed:", e);
        }
      }

      if (!cancelled) setLoading(false);
    }
    init();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  // ── Start lesson (user gesture needed for AudioContext) ──
  const handleStart = useCallback((fresh: boolean = false) => {
    freshStartRef.current = fresh;

    const ctx = new AudioContext();
    audioCtxRef.current = ctx;

    // Create the lockstep engine for bundled frame playback.
    // The third arg is a getter for iframe readiness — we pass a function
    // (not a value) so the engine reads the latest store state on every poll
    // without needing React subscriptions.
    engineRef.current = new LockstepEngine(
      ctx,
      {
        onSubtitle: (text, speaking) => {
          store.setTeacherSpeech(text, "teaching");
          store.setIsSpeaking(speaking);
        },
        onStepChange: (label) => {
          store.setCurrentStep(label);
        },
        onFrameDone: () => {
          sendFrameDone();
        },
        onError: (msg) => {
          console.error("[Lockstep]", msg);
        },
      },
      () => useClassroomStore.getState().iframeReady,
    );

    setStarted(true);
  }, [store, sendFrameDone]);

  // ── WebSocket connection ──
  useEffect(() => {
    if (!started || !token || !sessionId) return;

    function connect() {
      const wsUrl = BACKEND_URL.replace(/^http/, "ws");
      const freshParam = freshStartRef.current ? "&fresh=true" : "";
      const ws = new WebSocket(
        `${wsUrl}/teacher/ws/teach/${sessionId}?token=${token}${freshParam}`
      );
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("[WS] Connected");
        reconnectAttempts.current = 0;
        store.setStatus("active");
      };

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleServerMessage(msg);
      };

      ws.onclose = (e) => {
        console.log("[WS] Closed:", e.code);
        // Stop any playing audio to prevent overlap on reconnect
        stopAudio();
        console.log("[WS] Audio stopped");

        if (e.code === 4001 || e.code === 1000) return;
        // Reconnect
        if (reconnectAttempts.current < 5) {
          const delay = Math.pow(2, reconnectAttempts.current) * 1000;
          reconnectAttempts.current++;
          setTimeout(connect, delay);
        } else {
          store.setError("Connection lost. Please refresh.");
        }
      };

      ws.onerror = () => {
        console.error("[WS] Error");
      };
    }

    connect();

    return () => {
      // Cleanup: stop audio + close WS on unmount/HMR
      stopAudio();
      wsRef.current?.close(1000);
      wsRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [started, token, sessionId]);

  // ── Timer ──
  useEffect(() => {
    if (status === "active" && !timerRef.current) {
      timerRef.current = setInterval(() => store.incrementTimer(), 1000);
    }
    if (status !== "active" && timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [status, store]);

  // ── Handle server messages ──
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const handleServerMessage = useCallback((msg: Record<string, unknown>) => {
    const type = msg.type as string;
    console.log(`[MSG] ${type}`, type === "speak" ? (msg.text as string)?.slice(0, 60) : msg);

    switch (type) {
      case "session_info":
        store.setSessionInfo({
          sessionId: msg.session_id as string,
          lessonTitle: msg.lesson_title as string,
          totalFrames: msg.total_segments as number,
          isResuming: msg.is_resuming as boolean,
        });
        break;

      case "show_frame": {
        // Pre-show first frame BEFORE the opening speech (fixes empty-screen issue)
        const prev = useClassroomStore.getState().currentFrame;
        store.setCurrentFrame({
          id: msg.frame_id as string,
          url: msg.frame_url as string,
          index: prev?.index ?? 0,
          totalFrames: prev?.totalFrames ?? 0,
          progressPct: prev?.progressPct ?? 0,
        });
        if (!hasFirstFrame) setHasFirstFrame(true);
        console.log("[FRAME] URL set:", (msg.frame_url as string)?.slice(0, 80));
        break;
      }

      case "frame_bundle": {
        // The bundled lockstep payload — frontend engine handles all sync.
        const bundle = msg as unknown as FrameBundle;
        console.log(
          `[BUNDLE] ${bundle.frame_id} ${bundle.frame_index}/${bundle.total_frames}`,
          `${bundle.steps.length} steps`,
        );

        // FIX: If the frame URL is changing, reset iframeReady BEFORE
        // updating the store and starting playFrame(). Otherwise the
        // lockstep engine sees stale iframeReady=true from the previous
        // frame (React hasn't re-rendered yet) and sends play commands
        // to the old iframe content — which gets destroyed when React
        // re-renders, leaving the new frame frozen at t=0.
        const prevUrl = useClassroomStore.getState().currentFrame?.url;
        if (bundle.frame_url && bundle.frame_url !== prevUrl) {
          store.setIframeReady(false);
        }

        // Update UI state for the new frame
        store.setCurrentFrame({
          id: bundle.frame_id,
          url: bundle.frame_url,
          index: bundle.frame_index,
          totalFrames: bundle.total_frames,
          progressPct: bundle.progress_pct,
        });
        store.setFrameTitle(bundle.frame_title);
        store.setFallbackDescription(bundle.fallback_description);

        // Add the spoken text to the chat history (one entry per frame)
        const fullText = bundle.steps
          .map((s) => s.text)
          .filter(Boolean)
          .join(" ");
        if (fullText) {
          store.addMessage({
            role: "teacher",
            text: fullText,
            time: new Date().toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            }),
          });
        }

        if (!hasFirstFrame) setHasFirstFrame(true);

        // Run the lockstep engine — fire-and-forget. It calls onFrameDone
        // (-> sendFrameDone) when done.
        if (engineRef.current) {
          engineRef.current.playFrame(bundle).catch((e) => {
            console.error("[Lockstep] playFrame error:", e);
            // Still send frame_done so backend doesn't hang
            sendFrameDone();
          });
        } else {
          console.warn("[BUNDLE] no engine — sending frame_done immediately");
          sendFrameDone();
        }
        break;
      }

      case "frame_change": {
        // IMPORTANT: read URL from current state, NOT from closure (which is stale)
        const cur = useClassroomStore.getState().currentFrame;
        store.setCurrentFrame({
          id: msg.frame_id as string,
          url: cur?.url ?? "",
          index: msg.frame_index as number,
          totalFrames: msg.total_frames as number,
          progressPct: msg.progress_pct as number,
        });
        break;
      }

      case "seek_step":
        seekToStep(msg.label as string);
        store.setCurrentStep(msg.label as string);
        break;

      case "animation_control":
        if (msg.action === "play") playAnim();
        else if (msg.action === "pause") pauseAnim();
        break;

      case "speak_audio":
        playAudio(
          msg.audio as string,
          msg.text as string,
          msg.speech_type as string,
        );
        store.addMessage({
          role: "teacher",
          text: msg.text as string,
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        });
        break;

      case "speak":
        // Fallback: text-only speak (if TTS fails on backend)
        store.setTeacherSpeech(msg.text as string, msg.speech_type as string);
        store.addMessage({
          role: "teacher",
          text: msg.text as string,
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        });
        // Auto-send speech_done after 3s for text-only fallback
        setTimeout(() => sendSpeechDone(), 3000);
        break;

      case "ask_question":
        store.setCurrentQuestion({
          question: msg.question as string,
          questionType: msg.question_type as string,
          hints: msg.hints as string[],
          frameId: msg.segment_id as string,
          hintsShown: 0,
        });
        break;

      case "wait":
        // Visual indicator handled by avatar pulse
        break;

      case "session_complete":
        store.setSummary(msg.summary as Record<string, unknown>);
        break;

      case "error":
        store.setError(msg.message as string);
        break;
    }
  }, [store, seekToStep, playAnim, pauseAnim, playAudio, sendSpeechDone, sendFrameDone, hasFirstFrame]);

  // ── Send functions ──
  const send = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const handleSubmitAnswer = useCallback((text: string) => {
    send({ type: "response", text });
    store.setCurrentQuestion(null);
    store.addMessage({
      role: "student",
      text,
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    });
  }, [send, store]);

  const handleSendChat = useCallback((text: string) => {
    // If hand is raised, send as a question
    if (isHandRaised) {
      send({ type: "question", text });
      store.toggleHandRaised();
    } else {
      // Regular chat message — just log locally
      store.addMessage({
        role: "student",
        text,
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      });
    }
  }, [send, isHandRaised, store]);

  const handleToggleHand = useCallback(() => {
    const raising = !isHandRaised;
    store.toggleHandRaised();
    send({ type: raising ? "raise_hand" : "lower_hand" });
  }, [isHandRaised, store, send]);

  const handleTogglePause = useCallback(() => {
    const pausing = status === "active";
    store.setStatus(pausing ? "paused" : "active");
    send({ type: "control", action: pausing ? "pause" : "resume" });
    if (pausing) {
      engineRef.current?.pause();
      pauseAnim();
    } else {
      engineRef.current?.resume();
    }
  }, [status, store, send, pauseAnim]);

  const handleLeave = useCallback(() => {
    send({ type: "control", action: "leave" });
    engineRef.current?.stop();
    stopAudio();
    router.push("/dashboard");
  }, [send, stopAudio, router]);

  // ── Engine cleanup on unmount ──
  useEffect(() => {
    return () => {
      engineRef.current?.stop();
      engineRef.current = null;
    };
  }, []);

  // ── Render ──

  // Start screen — covers BOTH the pre-start state AND the preparing state
  // (after Start clicked but before first frame_bundle arrives)
  if (!started || !hasFirstFrame) {
    return (
      <StartScreen
        lessonTitle={lessonTitle}
        isLoading={loading}
        isPreparing={started && !hasFirstFrame}
        canResume={canResume}
        onStart={() => handleStart(false)}
        onStartOver={() => handleStart(true)}
      />
    );
  }

  // Completed screen
  if (status === "completed" && summary) {
    return (
      <div className="fixed inset-0 bg-[#0d1117] flex items-center justify-center">
        <div className="text-center space-y-6 max-w-md mx-4">
          <span className="material-symbols-rounded text-[#0d968b] text-[64px]">
            celebration
          </span>
          <h1 className="text-white text-2xl font-bold">Lesson Complete!</h1>
          <div className="text-white/60 space-y-2 text-sm">
            <p>Time: {(summary.time_spent_minutes as number)?.toFixed(0) ?? "?"} min</p>
            <p>Questions: {summary.questions_correct as number ?? 0}/{summary.questions_asked as number ?? 0} correct</p>
          </div>
          <button
            onClick={() => router.push("/dashboard")}
            className="px-6 py-3 bg-[#0d968b] hover:bg-[#0ba898] text-white rounded-xl font-medium"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  // Main classroom
  return (
    <div className="relative w-screen h-screen overflow-hidden">
      {/* Animation iframe with title overlay + failure fallback */}
      <AnimationFrame
        url={currentFrame?.url ?? ""}
        lessonTitle={lessonTitle}
        frameTitle={frameTitle}
        fallbackDescription={fallbackDescription}
      />

      {/* Top bar overlay */}
      <TopBar
        lessonTitle={lessonTitle}
        progressPct={currentFrame?.progressPct ?? 0}
        elapsedSeconds={elapsedSeconds}
      />

      {/* Avatar PiP */}
      <AvatarPiP ref={avatarRef} isSpeaking={isSpeaking} />

      {/* Subtitle overlay */}
      <SubtitleOverlay text={teacherSpeech} isSpeaking={isSpeaking} />

      {/* Question overlay */}
      {currentQuestion && (
        <QuestionOverlay
          question={currentQuestion.question}
          questionType={currentQuestion.questionType}
          hints={currentQuestion.hints}
          hintsShown={currentQuestion.hintsShown}
          onSubmit={handleSubmitAnswer}
          onShowHint={() => store.showNextHint()}
        />
      )}

      {/* Chat panel */}
      <ChatPanel
        isOpen={isChatOpen}
        messages={messages as DialogueEntry[]}
        onSendMessage={handleSendChat}
        onClose={() => store.toggleChat()}
      />

      {/* Control bar */}
      <ControlBar
        isMicOn={isMicOn}
        isChatOpen={isChatOpen}
        isHandRaised={isHandRaised}
        isPaused={status === "paused"}
        onToggleMic={() => store.toggleMic()}
        onToggleChat={() => store.toggleChat()}
        onToggleHand={handleToggleHand}
        onTogglePause={handleTogglePause}
        onLeave={handleLeave}
      />
    </div>
  );
}
