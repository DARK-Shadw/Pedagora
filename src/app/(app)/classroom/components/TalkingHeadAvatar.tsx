"use client";

import { useEffect, useRef, useState, useImperativeHandle, forwardRef } from "react";

/* eslint-disable @typescript-eslint/no-explicit-any */

export interface TalkingHeadAvatarHandle {
  speakAudio: (audioData: any) => boolean;
  setMood: (mood: string) => void;
  isReady: () => boolean;
}

interface TalkingHeadAvatarProps {
  onStartSpeaking?: () => void;
  onEndSpeaking?: () => void;
}

/**
 * 3D Ready Player Me avatar with lip-sync via TalkingHead.js.
 * Receives audio+viseme data from HeadTTS for real-time lip sync.
 */
const TalkingHeadAvatar = forwardRef<TalkingHeadAvatarHandle, TalkingHeadAvatarProps>(
  function TalkingHeadAvatar({ onStartSpeaking, onEndSpeaking }, ref) {
    const containerRef = useRef<HTMLDivElement>(null);
    const headRef = useRef<any>(null);
    const [isLoaded, setIsLoaded] = useState(false);
    const [loadError, setLoadError] = useState<string | null>(null);

    // Store callbacks in refs so useEffect doesn't re-run when parent re-renders
    const onStartRef = useRef(onStartSpeaking);
    const onEndRef = useRef(onEndSpeaking);
    onStartRef.current = onStartSpeaking;
    onEndRef.current = onEndSpeaking;

    // Expose methods to parent — speakAudio returns false if not ready
    useImperativeHandle(ref, () => ({
      speakAudio: (audioData: any): boolean => {
        if (headRef.current) {
          headRef.current.speakAudio(audioData, { lipsyncLang: "en" });
          return true;
        }
        return false;
      },
      setMood: (mood: string) => {
        headRef.current?.setMood(mood);
      },
      isReady: () => !!headRef.current,
    }));

    // Initialize ONCE — never re-run on parent re-renders
    useEffect(() => {
      if (!containerRef.current || headRef.current) return;

      let disposed = false;

      const init = async () => {
        try {
          // Load from CDN — npm import fails because TalkingHead uses
          // dynamic import() for lipsync modules that Turbopack can't resolve.
          const cdnUrl = `https://cdn.jsdelivr.net/npm/@met4citizen/talkinghead@1.7/modules/talkinghead.mjs`;
          const module = await (Function('url', 'return import(url)')(cdnUrl));
          const TalkingHead = module.TalkingHead;

          if (disposed) return;

          const head = new TalkingHead(containerRef.current!, {
            cameraView: "upper",
            cameraZoomEnable: false,
            cameraPanEnable: false,
            lipsyncModules: ["en"],
          });

          // Use refs for callbacks so they always point to latest function
          head.onstartspeaking = () => onStartRef.current?.();
          head.onendspeaking = () => onEndRef.current?.();

          // Load the avatar — matching official TalkingHead example config
          await head.showAvatar({
            url: "/models/professor-sage.glb",
            body: "F",
            avatarMood: "neutral",
          });

          if (disposed) {
            head.stop();
            return;
          }

          headRef.current = head;
          setIsLoaded(true);
          console.log("[Avatar] TalkingHead avatar loaded successfully");
        } catch (error) {
          console.error("[Avatar] Failed to initialize:", error);
          try {
            const container = containerRef.current;
            if (container) {
              const canvas = container.querySelector("canvas");
              if (canvas) canvas.remove();
            }
          } catch { /* cleanup best-effort */ }
          if (!disposed) {
            setLoadError(
              error instanceof Error ? error.message : "Failed to load avatar"
            );
          }
        }
      };

      init();

      return () => {
        disposed = true;
        headRef.current?.stop();
        headRef.current = null;
      };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    return (
      <div className="w-full h-full relative">
        {/* TalkingHead renders its Three.js canvas into this div */}
        <div
          ref={containerRef}
          className="w-full h-full"
          style={{ minHeight: "200px" }}
        />

        {/* Loading overlay */}
        {!isLoaded && !loadError && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#161b22]">
            <div className="w-8 h-8 border-2 border-[#0d968b] border-t-transparent rounded-full animate-spin" />
            <p className="text-xs text-[#8b949e] mt-2">Loading avatar...</p>
          </div>
        )}

        {/* Error fallback */}
        {loadError && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#161b22]">
            <div className="w-24 h-24 rounded-full bg-[#21262d] flex items-center justify-center">
              <span className="material-symbols-rounded text-5xl text-[#0d968b]">
                record_voice_over
              </span>
            </div>
            <p className="text-white font-medium mt-3">Professor Sage</p>
            <p className="text-xs text-[#8b949e] mt-1">Audio only mode</p>
          </div>
        )}
      </div>
    );
  }
);

export default TalkingHeadAvatar;
