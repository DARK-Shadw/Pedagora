"use client";

import { memo } from "react";
import { useClassroomStore } from "../stores/classroom-store";

interface ControlsProps {
  onRaiseHand: (name?: string) => void;
  onLowerHand: () => void;
  onReaction: (type: "got_it" | "confused" | "repeat") => void;
  onPause: () => void;
  onResume: () => void;
  onLeave: () => void;
}

export const Controls = memo(function Controls({
  onRaiseHand,
  onLowerHand,
  onReaction,
  onPause,
  onResume,
  onLeave,
}: ControlsProps) {
  const { isHandRaised, status, toggleHandRaised } = useClassroomStore();

  const handleHandToggle = () => {
    if (isHandRaised) {
      onLowerHand();
    } else {
      onRaiseHand();
    }
    toggleHandRaised();
  };

  return (
    <div className="flex items-center justify-between px-6 py-3 bg-[#0d1117] border-t border-[#30363d]">
      {/* Left: Reactions */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => onReaction("got_it")}
          className="flex items-center gap-1 px-3 py-1.5 bg-[#21262d] text-[#8b949e] text-sm rounded-lg hover:bg-[#30363d] hover:text-green-400 transition-colors"
          title="I get it!"
        >
          👍
        </button>
        <button
          onClick={() => onReaction("confused")}
          className="flex items-center gap-1 px-3 py-1.5 bg-[#21262d] text-[#8b949e] text-sm rounded-lg hover:bg-[#30363d] hover:text-yellow-400 transition-colors"
          title="I'm confused"
        >
          😕
        </button>
        <button
          onClick={() => onReaction("repeat")}
          className="flex items-center gap-1 px-3 py-1.5 bg-[#21262d] text-[#8b949e] text-sm rounded-lg hover:bg-[#30363d] hover:text-blue-400 transition-colors"
          title="Can you repeat that?"
        >
          🔁
        </button>
      </div>

      {/* Center: RYHTS */}
      <button
        onClick={handleHandToggle}
        className={`flex items-center gap-2 px-5 py-2.5 rounded-full text-sm font-medium transition-all ${
          isHandRaised
            ? "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 shadow-lg shadow-yellow-500/10"
            : "bg-[#21262d] text-[#8b949e] border border-[#30363d] hover:bg-[#30363d] hover:text-white"
        }`}
      >
        <span className="material-symbols-rounded text-xl">
          {isHandRaised ? "front_hand" : "back_hand"}
        </span>
        {isHandRaised ? "Hand Raised" : "Raise Hand"}
      </button>

      {/* Right: Session controls */}
      <div className="flex items-center gap-2">
        {status === "active" ? (
          <button
            onClick={onPause}
            className="flex items-center gap-1 px-3 py-1.5 bg-[#21262d] text-[#8b949e] text-sm rounded-lg hover:bg-[#30363d] transition-colors"
            title="Pause lesson"
          >
            <span className="material-symbols-rounded text-sm">pause</span>
            Pause
          </button>
        ) : status === "paused" ? (
          <button
            onClick={onResume}
            className="flex items-center gap-1 px-3 py-1.5 bg-[#0d968b]/20 text-[#0d968b] text-sm rounded-lg hover:bg-[#0d968b]/30 transition-colors"
            title="Resume lesson"
          >
            <span className="material-symbols-rounded text-sm">
              play_arrow
            </span>
            Resume
          </button>
        ) : null}
        <button
          onClick={onLeave}
          className="flex items-center gap-1 px-3 py-1.5 bg-red-500/10 text-red-400 text-sm rounded-lg hover:bg-red-500/20 transition-colors"
          title="Leave lesson"
        >
          <span className="material-symbols-rounded text-sm">
            call_end
          </span>
          Leave
        </button>
      </div>
    </div>
  );
});
