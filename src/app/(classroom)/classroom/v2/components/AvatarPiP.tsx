"use client";

import { forwardRef, memo, useEffect, useImperativeHandle, useRef, useState } from "react";

/* eslint-disable @typescript-eslint/no-explicit-any */

export interface AvatarPiPHandle {
  speakAudio: (audioData: any) => boolean;
}

interface AvatarPiPProps {
  isSpeaking: boolean;
}

/**
 * Small 80px circle PiP with TalkingHead.js 3D avatar.
 * Lip syncs with HeadTTS audio. Falls back to a pulsing circle on error.
 */
const AvatarPiPInner = forwardRef<AvatarPiPHandle, AvatarPiPProps>(
  function AvatarPiP({ isSpeaking }, ref) {
    const containerRef = useRef<HTMLDivElement>(null);
    const headRef = useRef<any>(null);
    const [loaded, setLoaded] = useState(false);
    const [error, setError] = useState(false);

    useImperativeHandle(ref, () => ({
      speakAudio: (audioData: any): boolean => {
        if (headRef.current) {
          headRef.current.speakAudio(audioData, { lipsyncLang: "en" });
          return true;
        }
        return false;
      },
    }));

    useEffect(() => {
      // TODO: Re-enable TalkingHead when ReadyPlayerMe CDN is reliable.
      // For now, use fallback speaking indicator.
      setError(true);
    }, []);

    return (
      <div
        className="absolute bottom-24 left-5 z-20"
        style={{ contain: "strict", width: 80, height: 80 }}
      >
        <div
          className={`
            w-20 h-20 rounded-full overflow-hidden
            border-2 transition-all duration-300
            ${isSpeaking ? "border-[#0d968b] shadow-lg shadow-[#0d968b]/30" : "border-white/10"}
          `}
        >
          {error ? (
            /* Fallback: simple speaking indicator */
            <div className="w-full h-full bg-[#161b22] flex items-center justify-center">
              <span
                className={`material-symbols-rounded text-[32px] transition-all ${
                  isSpeaking ? "text-[#0d968b] scale-110" : "text-white/30"
                }`}
              >
                {isSpeaking ? "graphic_eq" : "person"}
              </span>
            </div>
          ) : (
            <div
              ref={containerRef}
              className="w-full h-full bg-[#161b22]"
              style={{ opacity: loaded ? 1 : 0 }}
            />
          )}
        </div>

        {/* Speaking pulse ring */}
        {isSpeaking && !error && (
          <div className="absolute inset-0 rounded-full border-2 border-[#0d968b] animate-ping opacity-30" />
        )}
      </div>
    );
  }
);

export const AvatarPiP = memo(AvatarPiPInner);
