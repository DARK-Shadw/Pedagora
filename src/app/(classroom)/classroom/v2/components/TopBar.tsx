"use client";

import { memo, useEffect, useRef, useState } from "react";

interface TopBarProps {
  lessonTitle: string;
  progressPct: number;
  elapsedSeconds: number;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/**
 * Minimal top bar — lesson title, progress, timer.
 * Auto-hides after 3s of inactivity (mouse movement resets).
 */
function TopBarInner({ lessonTitle, progressPct, elapsedSeconds }: TopBarProps) {
  const [visible, setVisible] = useState(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    function show() {
      setVisible(true);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setVisible(false), 4000);
    }
    show();
    window.addEventListener("mousemove", show);
    window.addEventListener("touchstart", show);
    return () => {
      window.removeEventListener("mousemove", show);
      window.removeEventListener("touchstart", show);
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return (
    <div
      className={`
        absolute top-0 left-0 right-0 z-30
        flex items-center justify-between px-5 py-3
        bg-gradient-to-b from-black/60 to-transparent
        transition-opacity duration-500
        ${visible ? "opacity-100" : "opacity-0 pointer-events-none"}
      `}
    >
      {/* Left: title */}
      <div className="flex items-center gap-3 min-w-0">
        <span className="text-white/60 text-sm font-medium tracking-wide">Pedagora</span>
        <span className="text-white/30">|</span>
        <span className="text-white text-sm font-medium truncate max-w-[300px]">
          {lessonTitle}
        </span>
      </div>

      {/* Center: progress bar */}
      <div className="flex-1 max-w-[300px] mx-8">
        <div className="h-1 bg-white/10 rounded-full overflow-hidden">
          <div
            className="h-full bg-[#0d968b] rounded-full transition-all duration-700"
            style={{ width: `${Math.min(100, progressPct)}%` }}
          />
        </div>
      </div>

      {/* Right: timer */}
      <span className="text-white/50 text-sm font-mono tabular-nums">
        {formatTime(elapsedSeconds)}
      </span>
    </div>
  );
}

export const TopBar = memo(TopBarInner);
