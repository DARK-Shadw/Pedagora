"use client";

interface StartScreenProps {
  lessonTitle: string;
  isLoading: boolean;
  isPreparing?: boolean;
  canResume?: boolean;
  onStart: () => void;
  onStartOver?: () => void;
}

/**
 * Initial screen shown before the lesson starts.
 * Required because browser TTS needs a user gesture to initialize.
 *
 * States:
 *  - Loading: still authenticating / fetching session
 *  - Ready (fresh): single Start button
 *  - Ready (resumable): two buttons — Continue + Start Over
 *  - Preparing: user clicked Start, waiting for the first frame's audio bundle
 */
export function StartScreen({
  lessonTitle,
  isLoading,
  isPreparing = false,
  canResume = false,
  onStart,
  onStartOver,
}: StartScreenProps) {
  return (
    <div className="fixed inset-0 z-50 bg-[#0d1117] flex items-center justify-center">
      <div className="text-center space-y-8 max-w-md mx-4">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#0d968b] flex items-center justify-center">
            <span className="material-symbols-rounded text-white text-[24px]">
              school
            </span>
          </div>
          <span className="text-white text-xl font-semibold tracking-tight">
            Pedagora
          </span>
        </div>

        {/* Lesson title */}
        <div>
          <p className="text-white/40 text-sm mb-2">
            {isPreparing
              ? "Preparing your lesson"
              : canResume
                ? "Welcome back"
                : "Ready to learn"}
          </p>
          <h1 className="text-white text-2xl font-bold leading-tight">
            {lessonTitle || "Loading lesson..."}
          </h1>
        </div>

        {/* Action area */}
        {isPreparing ? (
          <div className="flex flex-col items-center gap-4">
            <span className="material-symbols-rounded animate-spin text-[#0d968b] text-[40px]">
              progress_activity
            </span>
            <p className="text-white/60 text-sm">
              Your AI teacher is getting ready...
            </p>
          </div>
        ) : canResume && onStartOver ? (
          <div className="flex flex-col gap-3">
            <button
              onClick={onStart}
              disabled={isLoading}
              className={`
                px-8 py-4 rounded-2xl text-lg font-semibold transition-all
                ${isLoading
                  ? "bg-white/5 text-white/30 cursor-wait"
                  : "bg-[#0d968b] hover:bg-[#0ba898] text-white hover:scale-105 active:scale-95 shadow-lg shadow-[#0d968b]/20"
                }
              `}
            >
              <span className="flex items-center gap-2">
                <span className="material-symbols-rounded text-[24px]">
                  resume
                </span>
                Continue Where I Left Off
              </span>
            </button>
            <button
              onClick={onStartOver}
              disabled={isLoading}
              className={`
                px-8 py-3 rounded-2xl text-sm font-semibold transition-all
                ${isLoading
                  ? "text-white/20 cursor-wait"
                  : "text-white/60 hover:text-white hover:bg-white/5"
                }
              `}
            >
              <span className="flex items-center gap-2 justify-center">
                <span className="material-symbols-rounded text-[20px]">
                  restart_alt
                </span>
                Start Over from the Beginning
              </span>
            </button>
          </div>
        ) : (
          <button
            onClick={onStart}
            disabled={isLoading}
            className={`
              px-8 py-4 rounded-2xl text-lg font-semibold transition-all
              ${isLoading
                ? "bg-white/5 text-white/30 cursor-wait"
                : "bg-[#0d968b] hover:bg-[#0ba898] text-white hover:scale-105 active:scale-95 shadow-lg shadow-[#0d968b]/20"
              }
            `}
          >
            {isLoading ? (
              <span className="flex items-center gap-2">
                <span className="material-symbols-rounded animate-spin text-[20px]">
                  progress_activity
                </span>
                Connecting...
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <span className="material-symbols-rounded text-[24px]">
                  play_circle
                </span>
                Start Lesson
              </span>
            )}
          </button>
        )}

        {!isPreparing && (
          <p className="text-white/20 text-xs">
            Click to start. Audio will be enabled for the AI teacher.
          </p>
        )}
      </div>
    </div>
  );
}
