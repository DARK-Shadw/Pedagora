"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
import { useClassroomStore } from "../stores/classroom-store";

interface AnimationFrameProps {
  url: string;
  lessonTitle: string;
  frameTitle: string;
  fallbackDescription: string;
  onStepChange?: (label: string) => void;
  onLoad?: () => void;
}

const FAILURE_TIMEOUT_MS = 12000;

/**
 * Renders the animation HTML in an iframe with:
 *  - Always-visible title overlay (top-left)
 *  - Failure detection: if no `stepChanged` event from the iframe within 3s
 *    of URL change, show a fallback panel with title + description
 *  - postMessage forwarding for the lockstep engine
 */
function AnimationFrameInner({
  url,
  lessonTitle,
  frameTitle,
  fallbackDescription,
  onStepChange,
  onLoad,
}: AnimationFrameProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [hasFailed, setHasFailed] = useState(false);
  const [hasRendered, setHasRendered] = useState(false);
  const setIframeReady = useClassroomStore((s) => s.setIframeReady);
  const setIframeLabels = useClassroomStore((s) => s.setIframeLabels);

  // Reset failure detection on each new URL.
  // Also clear the store iframeReady flag so the lockstep engine waits
  // until the new iframe document publishes its first stepChanged event.
  useEffect(() => {
    if (!url) return;
    setHasFailed(false);
    setHasRendered(false);
    setIframeReady(false);
    setIframeLabels([]);
    const timer = setTimeout(() => {
      setHasFailed((prev) => (hasRendered ? prev : true));
    }, FAILURE_TIMEOUT_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  // Listen for stepChanged events from the iframe.
  // The first event proves the GSAP timeline + notifier are alive — publish
  // that to the store so the lockstep engine can poll for it instead of
  // racing with its own message listener.
  useEffect(() => {
    function handleMessage(e: MessageEvent) {
      const evt = e.data?.event;
      if (evt === "stepChanged") {
        if (!hasRendered) setHasRendered(true);
        setIframeReady(true);
        if (onStepChange) onStepChange(e.data.label);
      } else if (evt === "iframeReady") {
        if (!hasRendered) setHasRendered(true);
        setIframeReady(true);
        if (Array.isArray(e.data.labels)) {
          setIframeLabels(e.data.labels);
        }
      }
    }
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [onStepChange, hasRendered, setIframeReady, setIframeLabels]);

  const handleIframeError = useCallback(() => {
    setHasFailed(true);
  }, []);

  const handleIframeLoad = useCallback(() => {
    if (onLoad) onLoad();
  }, [onLoad]);

  return (
    <div className="absolute inset-0 bg-[#0d1117]">
      {/* Title overlay — ALWAYS visible (fixes the empty-screen complaint) */}
      {(lessonTitle || frameTitle) && (
        <div className="absolute top-6 left-6 z-30 bg-black/60 backdrop-blur-md px-4 py-2.5 rounded-lg border border-white/10 max-w-md">
          {lessonTitle && (
            <div className="text-white/40 text-[10px] uppercase tracking-widest font-bold">
              {lessonTitle}
            </div>
          )}
          {frameTitle && (
            <div className="text-white text-sm font-bold mt-0.5 line-clamp-2">
              {frameTitle}
            </div>
          )}
        </div>
      )}

      {/* Iframe */}
      <iframe
        ref={iframeRef}
        src={url || undefined}
        onLoad={handleIframeLoad}
        onError={handleIframeError}
        className="absolute inset-0 w-full h-full border-0"
        style={{ willChange: "transform" }}
        allow="autoplay"
        loading="eager"
        title="Animation"
      />

      {/* Fallback overlay if animation broken */}
      {hasFailed && !hasRendered && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-[#0d1117] text-center px-8 pt-24">
          <div className="size-16 rounded-2xl bg-[#0d968b]/10 text-[#0d968b] flex items-center justify-center mb-6">
            <span className="material-symbols-rounded text-3xl">slideshow</span>
          </div>
          <h2 className="text-white text-xl font-bold mb-3 max-w-2xl">
            {frameTitle || "This concept"}
          </h2>
          {fallbackDescription && (
            <p className="text-white/60 max-w-md text-sm leading-relaxed">
              {fallbackDescription}
            </p>
          )}
          <p className="text-white/30 text-xs mt-6">
            Listen to your AI teacher explain this concept.
          </p>
        </div>
      )}

      {/* Loading state when no URL yet (replaces "Waiting for animation...") */}
      {!url && (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-8">
          <div className="size-16 rounded-2xl bg-[#0d968b]/10 text-[#0d968b] flex items-center justify-center mb-6 animate-pulse">
            <span className="material-symbols-rounded text-3xl">school</span>
          </div>
          <p className="text-white/60 text-sm">Preparing your lesson...</p>
        </div>
      )}
    </div>
  );
}

export const AnimationFrame = memo(AnimationFrameInner);

/**
 * Hook to send commands to the animation iframe.
 * Kept separate so the iframe component doesn't re-render on command changes.
 */
export function useAnimationCommands() {
  const send = useCallback((action: string, label?: string) => {
    const iframe = document.querySelector<HTMLIFrameElement>(
      'iframe[title="Animation"]'
    );
    if (!iframe?.contentWindow) return;
    const msg: Record<string, string> = { action };
    if (label) msg.label = label;
    iframe.contentWindow.postMessage(msg, "*");
  }, []);

  const seekToStep = useCallback(
    (label: string) => send("seekToStep", label),
    [send]
  );
  const play = useCallback(() => send("play"), [send]);
  const pause = useCallback(() => send("pause"), [send]);

  return { seekToStep, play, pause };
}
