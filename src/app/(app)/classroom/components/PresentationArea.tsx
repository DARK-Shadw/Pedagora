"use client";

import { useEffect, useRef } from "react";
import { useClassroomStore } from "../stores/classroom-store";

export function PresentationArea() {
  const { currentAnimation, teacherSpeech, isSpeaking } = useClassroomStore();
  const videoRef = useRef<HTMLVideoElement>(null);

  // Handle animation commands
  useEffect(() => {
    if (!currentAnimation || !videoRef.current) return;

    const video = videoRef.current;

    if (currentAnimation.url && video.src !== currentAnimation.url) {
      video.src = currentAnimation.url;
      video.load();
    }

    switch (currentAnimation.action) {
      case "play":
        video.play().catch(() => {});
        break;
      case "pause":
        video.pause();
        break;
      case "rewind":
        video.currentTime = 0;
        video.play().catch(() => {});
        break;
    }
  }, [currentAnimation]);

  return (
    <div className="flex-1 flex flex-col bg-[#0d1117] rounded-lg overflow-hidden">
      {/* Video/Animation area */}
      <div className="flex-1 flex items-center justify-center relative">
        {currentAnimation?.url ? (
          <video
            ref={videoRef}
            className="max-w-full max-h-full object-contain"
            playsInline
            onEnded={() => {
              useClassroomStore.getState().setCurrentAnimation(null);
            }}
          />
        ) : (
          <div className="flex flex-col items-center gap-3 text-[#8b949e]">
            <span className="material-symbols-rounded text-5xl">
              play_circle
            </span>
            <p className="text-sm">
              {isSpeaking
                ? "Teacher is explaining..."
                : "Animations will appear here"}
            </p>
          </div>
        )}
      </div>

      {/* Teacher speech subtitle */}
      {teacherSpeech && (
        <div className="px-4 py-3 bg-[#161b22] border-t border-[#30363d]">
          <div className="flex items-start gap-2">
            <span className="material-symbols-rounded text-[#0d968b] text-sm mt-0.5">
              {teacherSpeech.type === "question"
                ? "help"
                : teacherSpeech.type === "feedback"
                ? "chat"
                : "record_voice_over"}
            </span>
            <p className="text-sm text-[#c9d1d9] leading-relaxed">
              {teacherSpeech.text}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
