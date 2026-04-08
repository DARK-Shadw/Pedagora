"use client";

import { memo } from "react";

interface SubtitleOverlayProps {
  text: string;
  isSpeaking: boolean;
}

/**
 * Teacher speech displayed as a subtitle overlay at the bottom of the visual area.
 * Fades in/out with the speech. Clean, readable, non-intrusive.
 */
function SubtitleOverlayInner({ text, isSpeaking }: SubtitleOverlayProps) {
  if (!text) return null;

  return (
    <div
      className={`
        absolute bottom-20 left-1/2 -translate-x-1/2
        max-w-[80%] px-5 py-3
        bg-black/70 backdrop-blur-sm rounded-xl
        text-white text-base leading-relaxed text-center
        transition-opacity duration-300
        ${isSpeaking ? "opacity-100" : "opacity-60"}
      `}
    >
      {text}
    </div>
  );
}

export const SubtitleOverlay = memo(SubtitleOverlayInner);
