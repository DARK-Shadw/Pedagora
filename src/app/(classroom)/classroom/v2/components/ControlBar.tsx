"use client";

import { memo } from "react";

interface ControlBarProps {
  isMicOn: boolean;
  isChatOpen: boolean;
  isHandRaised: boolean;
  isPaused: boolean;
  onToggleMic: () => void;
  onToggleChat: () => void;
  onToggleHand: () => void;
  onTogglePause: () => void;
  onLeave: () => void;
}

/**
 * Floating bottom control bar — Google Meet style.
 * 5 buttons: Mic, Chat, Raise Hand, Pause, Leave.
 */
function ControlBarInner({
  isMicOn,
  isChatOpen,
  isHandRaised,
  isPaused,
  onToggleMic,
  onToggleChat,
  onToggleHand,
  onTogglePause,
  onLeave,
}: ControlBarProps) {
  return (
    <div className="absolute bottom-0 left-0 right-0 z-30 flex justify-center pb-5">
      <div className="flex items-center gap-3 px-5 py-3 bg-[#1a1f2e]/90 backdrop-blur-md rounded-2xl shadow-2xl">
        {/* Mic */}
        <ControlButton
          icon={isMicOn ? "mic" : "mic_off"}
          label={isMicOn ? "Mute" : "Unmute"}
          active={isMicOn}
          onClick={onToggleMic}
        />

        {/* Chat */}
        <ControlButton
          icon="chat"
          label="Chat"
          active={isChatOpen}
          onClick={onToggleChat}
        />

        {/* Raise Hand */}
        <ControlButton
          icon="front_hand"
          label={isHandRaised ? "Lower Hand" : "Raise Hand"}
          active={isHandRaised}
          activeColor="text-amber-400"
          onClick={onToggleHand}
        />

        {/* Pause / Resume */}
        <ControlButton
          icon={isPaused ? "play_arrow" : "pause"}
          label={isPaused ? "Resume" : "Pause"}
          active={false}
          onClick={onTogglePause}
        />

        {/* Divider */}
        <div className="w-px h-8 bg-white/10 mx-1" />

        {/* Leave */}
        <button
          onClick={onLeave}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-red-600 hover:bg-red-500 text-white text-sm font-medium transition-colors"
          title="Leave Classroom"
        >
          <span className="material-symbols-rounded text-[20px]">call_end</span>
          <span className="hidden sm:inline">Leave</span>
        </button>
      </div>
    </div>
  );
}

function ControlButton({
  icon,
  label,
  active,
  activeColor = "text-[#0d968b]",
  onClick,
}: {
  icon: string;
  label: string;
  active: boolean;
  activeColor?: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`
        relative flex items-center justify-center
        w-12 h-12 rounded-full transition-all
        ${active
          ? `bg-white/15 ${activeColor}`
          : "bg-white/5 text-white/70 hover:bg-white/10 hover:text-white"
        }
      `}
      title={label}
    >
      <span className="material-symbols-rounded text-[22px]">{icon}</span>
    </button>
  );
}

export const ControlBar = memo(ControlBarInner);
