"use client";

import { memo, useState } from "react";

interface QuestionOverlayProps {
  question: string;
  questionType: string;
  hints: string[];
  hintsShown: number;
  onSubmit: (answer: string) => void;
  onShowHint: () => void;
}

/**
 * Centered overlay when teacher asks a question.
 * Shows question text, answer input, submit button, and hints.
 */
function QuestionOverlayInner({
  question,
  questionType,
  hints,
  hintsShown,
  onSubmit,
  onShowHint,
}: QuestionOverlayProps) {
  const [answer, setAnswer] = useState("");

  function handleSubmit() {
    if (!answer.trim()) return;
    onSubmit(answer.trim());
    setAnswer("");
  }

  return (
    <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-lg mx-4 bg-[#161b22] border border-white/10 rounded-2xl shadow-2xl p-6 space-y-4">
        {/* Question type badge */}
        <div className="flex items-center gap-2">
          <span className="material-symbols-rounded text-[#0d968b] text-[20px]">
            help_outline
          </span>
          <span className="text-[#0d968b] text-xs font-medium uppercase tracking-wider">
            {questionType}
          </span>
        </div>

        {/* Question text */}
        <p className="text-white text-lg leading-relaxed">{question}</p>

        {/* Hints shown */}
        {hintsShown > 0 && hints.length > 0 && (
          <div className="space-y-2">
            {hints.slice(0, hintsShown).map((hint, i) => (
              <div
                key={i}
                className="flex items-start gap-2 text-amber-400/80 text-sm bg-amber-400/5 rounded-lg px-3 py-2"
              >
                <span className="material-symbols-rounded text-[16px] mt-0.5">
                  lightbulb
                </span>
                <span>{hint}</span>
              </div>
            ))}
          </div>
        )}

        {/* Answer input */}
        <div className="flex gap-3">
          <input
            type="text"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            placeholder="Type your answer..."
            className="flex-1 px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder:text-white/30 focus:outline-none focus:border-[#0d968b]/50 focus:ring-1 focus:ring-[#0d968b]/20"
            autoFocus
          />
          <button
            onClick={handleSubmit}
            disabled={!answer.trim()}
            className="px-6 py-3 bg-[#0d968b] hover:bg-[#0ba898] disabled:opacity-40 disabled:cursor-not-allowed text-white font-medium rounded-xl transition-colors"
          >
            Submit
          </button>
        </div>

        {/* Hint button */}
        {hintsShown < hints.length && (
          <button
            onClick={onShowHint}
            className="flex items-center gap-1.5 text-amber-400/60 hover:text-amber-400 text-sm transition-colors"
          >
            <span className="material-symbols-rounded text-[16px]">lightbulb</span>
            Show hint ({hints.length - hintsShown} remaining)
          </button>
        )}
      </div>
    </div>
  );
}

export const QuestionOverlay = memo(QuestionOverlayInner);
