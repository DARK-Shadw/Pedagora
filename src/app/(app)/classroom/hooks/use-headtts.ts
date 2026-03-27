"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/* eslint-disable @typescript-eslint/no-explicit-any */

const CDN_BASE =
  "https://cdn.jsdelivr.net/npm/@met4citizen/headtts@1.2";

/**
 * Hook for Kokoro neural TTS via HeadTTS (@met4citizen/headtts).
 *
 * Runs Kokoro neural inference in-browser via WebGPU or WASM.
 * Falls back to browser SpeechSynthesis only if HeadTTS completely fails.
 */
export function useHeadTTS() {
  const [isLoaded, setIsLoaded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [usesFallback, setUsesFallback] = useState(false);
  const [loadProgress, setLoadProgress] = useState(0);

  const ttsRef = useRef<any>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const onEndCallbackRef = useRef<(() => void) | null>(null);
  const initPromiseRef = useRef<Promise<void> | null>(null);
  const avatarRef = useRef<{ speakAudio: (data: any) => void } | null>(null);

  const initialize = useCallback(async () => {
    if (initPromiseRef.current) return;

    const doInit = async () => {
      // Always unlock browser TTS as safety net (requires user gesture)
      try {
        const unlock = new SpeechSynthesisUtterance("");
        unlock.volume = 0;
        window.speechSynthesis?.speak(unlock);
      } catch {
        // ignore
      }

      setIsLoading(true);
      setLoadProgress(0);

      // Skip HeadTTS entirely if no WebGPU — WASM fallback is unusably slow (10+ min)
      if (!(navigator as any).gpu) {
        console.warn("[HeadTTS] No WebGPU support — using browser TTS");
        setUsesFallback(true);
        setIsLoaded(true);
        setIsLoading(false);
        return;
      }

      try {
        const { HeadTTS } = await import("@met4citizen/headtts");

        const audioCtx = new AudioContext();
        audioCtxRef.current = audioCtx;

        // workerModule MUST be set to CDN URL — without it, HeadTTS tries
        // import.meta.url which breaks under Turbopack bundling
        const headtts = new HeadTTS({
          // WebGPU preferred (1-3s synthesis), WASM fallback (10+ min — unusable).
          // WebGPU runs in Web Worker, so no conflict with TalkingHead's WebGL.
          endpoints: ["webgpu", "wasm"],
          languages: ["en-us"],
          voices: ["af_bella"],
          audioCtx,
          workerModule: `${CDN_BASE}/modules/worker-tts.mjs`,
          dictionaryURL: `${CDN_BASE}/dictionaries/`,
          trace: 0,
        });

        headtts.onstart = () => setIsSpeaking(true);
        headtts.onend = () => {
          setIsSpeaking(false);
          onEndCallbackRef.current?.();
          onEndCallbackRef.current = null;
        };
        headtts.onerror = (error: any) => {
          console.error("[HeadTTS] Error:", error);
          setIsSpeaking(false);
          onEndCallbackRef.current?.();
          onEndCallbackRef.current = null;
        };

        console.log("[HeadTTS] Connecting... (model will download on first use)");

        await headtts.connect(null, (progress: any) => {
          if (progress?.loaded && progress?.total) {
            const pct = Math.round((progress.loaded / progress.total) * 100);
            setLoadProgress(pct);
            if (pct % 10 === 0) {
              console.log(`[HeadTTS] Model download: ${pct}%`);
            }
          }
        });

        await headtts.setup({
          voice: "af_bella",
          language: "en-us",
          speed: 1,
          audioEncoding: "wav",
        });

        ttsRef.current = headtts;
        setUsesFallback(false);
        console.log("[HeadTTS] Ready — Kokoro neural TTS active");
      } catch (error) {
        console.error("[HeadTTS] Init failed:", error);
        setUsesFallback(true);
      } finally {
        setIsLoaded(true);
        setIsLoading(false);
      }
    };

    initPromiseRef.current = doInit();
    await initPromiseRef.current;
  }, []);

  const onStartCallbackRef = useRef<(() => void) | null>(null);

  const speak = useCallback(
    (text: string, onEnd?: () => void, onStart?: () => void) => {
      onEndCallbackRef.current = onEnd || null;
      onStartCallbackRef.current = onStart || null;

      // HeadTTS path
      if (ttsRef.current && !usesFallback) {
        if (audioCtxRef.current?.state === "suspended") {
          audioCtxRef.current.resume();
        }

        // Split into sentences for shorter GPU bursts (reduces avatar stutter)
        const sentences = text.match(/[^.!?]+[.!?]+/g) || [text];

        let startFired = false;
        const audioHandler = (message: any) => {
          if (message.type === "audio" && message.data) {
            // Fire onStart on first audio chunk (subtitle appears with audio)
            if (!startFired) {
              startFired = true;
              onStartCallbackRef.current?.();
              onStartCallbackRef.current = null;
            }
            // Try avatar first — it handles audio + lip sync together
            const avatarPlayed = avatarRef.current?.speakAudio(message.data);

            if (!avatarPlayed && message.data.audio && audioCtxRef.current) {
              // No avatar or not ready — play AudioBuffer directly
              try {
                if (audioCtxRef.current.state !== "running") {
                  audioCtxRef.current.resume();
                }
                const source = audioCtxRef.current.createBufferSource();
                source.buffer = message.data.audio;
                source.connect(audioCtxRef.current.destination);
                source.start();
              } catch (e) {
                console.error("[HeadTTS] Audio playback error:", e);
              }
            }
          } else if (message.type === "error") {
            console.error("[HeadTTS] Synthesis error:", message.data);
          }
        };

        // Synthesize each sentence separately for shorter GPU bursts
        ttsRef.current.onmessage = audioHandler;
        for (const sentence of sentences) {
          const trimmed = sentence.trim();
          if (trimmed) {
            ttsRef.current.synthesize({ input: trimmed }, audioHandler);
          }
        }
        return;
      }

      // Fallback: browser SpeechSynthesis
      if (!window.speechSynthesis) {
        onEnd?.();
        return;
      }

      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 0.95;
      utterance.pitch = 1.0;
      utterance.volume = 1.0;

      const voices = window.speechSynthesis.getVoices();
      const preferred = voices.find(
        (v) =>
          v.lang.startsWith("en") &&
          (v.name.includes("Google") ||
            v.name.includes("Microsoft") ||
            v.name.includes("Natural"))
      );
      if (preferred) utterance.voice = preferred;

      utterance.onstart = () => {
        setIsSpeaking(true);
        onStartCallbackRef.current?.();
        onStartCallbackRef.current = null;
      };
      utterance.onend = () => {
        setIsSpeaking(false);
        onEndCallbackRef.current?.();
        onEndCallbackRef.current = null;
      };
      utterance.onerror = () => {
        setIsSpeaking(false);
        onEndCallbackRef.current?.();
        onEndCallbackRef.current = null;
      };

      window.speechSynthesis.speak(utterance);
    },
    [usesFallback]
  );

  const stop = useCallback(() => {
    if (ttsRef.current && !usesFallback) {
      ttsRef.current.clear();
    }
    window.speechSynthesis?.cancel();
    setIsSpeaking(false);
    onEndCallbackRef.current = null;
  }, [usesFallback]);

  useEffect(() => {
    return () => {
      ttsRef.current?.clear();
      audioCtxRef.current?.close();
    };
  }, []);

  const setAvatar = useCallback(
    (avatar: { speakAudio: (data: any) => void } | null) => {
      avatarRef.current = avatar;
    },
    []
  );

  return {
    isLoaded,
    isLoading,
    isSpeaking,
    usesFallback,
    loadProgress,
    initialize,
    speak,
    stop,
    setAvatar,
    ttsRef,
  };
}
