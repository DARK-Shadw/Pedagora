"use client";

import { useCallback, useEffect, useRef } from "react";

/**
 * Controls the animation iframe via postMessage.
 * Listens for stepChanged events from the iframe.
 */
export function useAnimationFrame(onStepChange?: (label: string) => void) {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Send postMessage commands to iframe
  const seekToStep = useCallback((label: string) => {
    iframeRef.current?.contentWindow?.postMessage({ action: "seekToStep", label }, "*");
  }, []);

  const play = useCallback(() => {
    iframeRef.current?.contentWindow?.postMessage({ action: "play" }, "*");
  }, []);

  const pause = useCallback(() => {
    iframeRef.current?.contentWindow?.postMessage({ action: "pause" }, "*");
  }, []);

  // Listen for stepChanged events from iframe
  useEffect(() => {
    function handleMessage(e: MessageEvent) {
      if (e.data?.event === "stepChanged" && onStepChange) {
        onStepChange(e.data.label);
      }
    }
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [onStepChange]);

  return { iframeRef, seekToStep, play, pause };
}
