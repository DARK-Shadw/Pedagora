"use client";

import { useCallback, useEffect, useRef } from "react";
import { useClassroomStore } from "../stores/classroom-store";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
const WS_URL = BACKEND_URL.replace("http", "ws");

export function useTeacherSession(sessionId: string, token: string) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;

  const {
    setSessionInfo,
    setStatus,
    setTeacherSpeech,
    setCurrentAnimation,
    setCurrentQuestion,
    setCurrentSegment,
    setIsWaiting,
    setSessionSummary,
    setError,
    addDialogue,
  } = useClassroomStore();

  const connect = useCallback(() => {
    if (!sessionId || !token) return;

    const ws = new WebSocket(
      `${WS_URL}/teacher/ws/teach/${sessionId}?token=${token}`
    );
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("[WS] Connected to teacher session");
      reconnectAttempts.current = 0;
      setStatus("active");
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
      } catch (e) {
        console.error("[WS] Failed to parse message:", e);
      }
    };

    ws.onclose = (event) => {
      console.log("[WS] Disconnected:", event.code, event.reason);
      wsRef.current = null;

      if (event.code === 4001) {
        setError("Authentication failed");
        return;
      }

      if (
        reconnectAttempts.current < maxReconnectAttempts &&
        event.code !== 1000
      ) {
        const delay = Math.min(
          1000 * Math.pow(2, reconnectAttempts.current),
          30000
        );
        reconnectAttempts.current++;
        console.log(
          `[WS] Reconnecting in ${delay}ms (attempt ${reconnectAttempts.current})`
        );
        setStatus("connecting");
        setTimeout(connect, delay);
      } else if (event.code !== 1000) {
        setError("Connection lost. Please refresh the page.");
      }
    };

    ws.onerror = (error) => {
      console.error("[WS] Error:", error);
    };
  }, [sessionId, token, setSessionInfo, setStatus, setError]);

  const handleMessage = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (msg: any) => {
      switch (msg.type) {
        case "session_info":
          setSessionInfo({
            sessionId: msg.session_id,
            lessonTitle: msg.lesson_title,
            totalSegments: msg.total_segments,
            isResuming: msg.is_resuming,
          });
          break;

        case "speak":
          setTeacherSpeech({
            text: msg.text,
            type: msg.speech_type,
            segmentId: msg.segment_id || "",
          });
          addDialogue({
            role: "teacher",
            text: msg.text,
            timestamp: new Date().toISOString(),
          });
          break;

        case "show_animation":
          setCurrentAnimation({
            animationId: msg.animation_id,
            url: msg.animation_url,
            action: msg.action,
            durationSeconds: msg.duration_seconds,
          });
          break;

        case "ask_question":
          setCurrentQuestion({
            question: msg.question,
            questionType: msg.question_type,
            hints: msg.hints || [],
            segmentId: msg.segment_id || "",
            hintsShown: 0,
          });
          break;

        case "segment_change":
          setCurrentSegment({
            id: msg.segment_id,
            type: msg.segment_type,
            title: msg.segment_title || "",
            progressPct: msg.progress_pct,
          });
          // Clear question when moving to new segment
          setCurrentQuestion(null);
          break;

        case "wait":
          setIsWaiting(true, msg.reason);
          setTimeout(() => setIsWaiting(false), msg.seconds * 1000);
          break;

        case "session_complete":
          setSessionSummary(msg.summary);
          break;

        case "error":
          if (!msg.recoverable) {
            setError(msg.message);
          } else {
            console.warn("[Teacher] Recoverable error:", msg.message);
          }
          break;

        default:
          console.log("[WS] Unknown message type:", msg.type);
      }
    },
    [
      setSessionInfo,
      setTeacherSpeech,
      setCurrentAnimation,
      setCurrentQuestion,
      setCurrentSegment,
      setIsWaiting,
      setSessionSummary,
      setError,
      addDialogue,
    ]
  );

  // Send messages to backend
  const sendMessage = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (msg: Record<string, any>) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify(msg));
      }
    },
    []
  );

  const sendResponse = useCallback(
    (text: string, segmentId: string = "") => {
      sendMessage({ type: "response", text, segment_id: segmentId });
      addDialogue({
        role: "student",
        text,
        timestamp: new Date().toISOString(),
      });
    },
    [sendMessage, addDialogue]
  );

  const raiseHand = useCallback(
    (studentName: string = "") => {
      sendMessage({ type: "raise_hand", student_name: studentName });
    },
    [sendMessage]
  );

  const lowerHand = useCallback(() => {
    sendMessage({ type: "lower_hand" });
  }, [sendMessage]);

  const sendReaction = useCallback(
    (reactionType: "got_it" | "confused" | "repeat") => {
      sendMessage({ type: "reaction", reaction_type: reactionType });
    },
    [sendMessage]
  );

  const sendQuestion = useCallback(
    (text: string) => {
      sendMessage({ type: "question", text });
      addDialogue({
        role: "student",
        text: `[Question] ${text}`,
        timestamp: new Date().toISOString(),
      });
    },
    [sendMessage, addDialogue]
  );

  const pauseSession = useCallback(() => {
    sendMessage({ type: "control", action: "pause" });
    setStatus("paused");
  }, [sendMessage, setStatus]);

  const resumeSession = useCallback(() => {
    sendMessage({ type: "control", action: "resume" });
    setStatus("active");
  }, [sendMessage, setStatus]);

  const leaveSession = useCallback(() => {
    sendMessage({ type: "control", action: "leave" });
    wsRef.current?.close(1000);
  }, [sendMessage]);

  // Connect on mount
  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close(1000);
    };
  }, [connect]);

  // Timer
  useEffect(() => {
    const store = useClassroomStore.getState();
    if (store.status !== "active") return;

    const interval = setInterval(() => {
      useClassroomStore.getState().incrementTimer();
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  return {
    sendResponse,
    raiseHand,
    lowerHand,
    sendReaction,
    sendQuestion,
    pauseSession,
    resumeSession,
    leaveSession,
  };
}
