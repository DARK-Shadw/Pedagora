"use client";

import { useClassroomStore } from "../stores/classroom-store";

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function SessionHeader() {
  const { lessonTitle, currentSegment, elapsedSeconds, status, totalSegments } =
    useClassroomStore();

  const progressPct = currentSegment?.progressPct ?? 0;

  return (
    <div className="flex items-center justify-between px-6 py-3 bg-[#161b22] border-b border-[#30363d]">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="material-symbols-rounded text-[#0d968b] text-xl">
            school
          </span>
          <h1 className="text-white font-medium text-sm truncate max-w-[300px]">
            {lessonTitle || "Loading lesson..."}
          </h1>
        </div>
        {currentSegment && (
          <span className="text-xs text-[#8b949e] bg-[#21262d] px-2 py-1 rounded">
            {currentSegment.type} — {currentSegment.title}
          </span>
        )}
      </div>

      <div className="flex items-center gap-6">
        {/* Progress bar */}
        <div className="flex items-center gap-2">
          <div className="w-32 h-1.5 bg-[#21262d] rounded-full overflow-hidden">
            <div
              className="h-full bg-[#0d968b] rounded-full transition-all duration-500"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <span className="text-xs text-[#8b949e]">
            {Math.round(progressPct)}%
          </span>
        </div>

        {/* Timer */}
        <div className="flex items-center gap-1 text-[#8b949e]">
          <span className="material-symbols-rounded text-sm">timer</span>
          <span className="text-xs font-mono">
            {formatTime(elapsedSeconds)}
          </span>
        </div>

        {/* Status indicator */}
        <div className="flex items-center gap-1.5">
          <div
            className={`w-2 h-2 rounded-full ${
              status === "active"
                ? "bg-green-500"
                : status === "paused"
                ? "bg-yellow-500"
                : status === "connecting"
                ? "bg-blue-500 animate-pulse"
                : status === "completed"
                ? "bg-[#0d968b]"
                : "bg-red-500"
            }`}
          />
          <span className="text-xs text-[#8b949e] capitalize">{status}</span>
        </div>
      </div>
    </div>
  );
}
