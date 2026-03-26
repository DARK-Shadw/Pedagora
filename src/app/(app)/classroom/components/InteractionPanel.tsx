"use client";

import { useState } from "react";
import { useClassroomStore } from "../stores/classroom-store";

interface InteractionPanelProps {
  onSubmitResponse: (text: string, segmentId?: string) => void;
  onSubmitQuestion: (text: string) => void;
}

export function InteractionPanel({
  onSubmitResponse,
  onSubmitQuestion,
}: InteractionPanelProps) {
  const {
    currentQuestion,
    isHandRaised,
    showNextHint,
    dialogueHistory,
    isWaiting,
    waitReason,
    status,
  } = useClassroomStore();
  const [inputText, setInputText] = useState("");
  const [questionText, setQuestionText] = useState("");

  const handleSubmitResponse = () => {
    if (!inputText.trim()) return;
    onSubmitResponse(inputText.trim(), currentQuestion?.segmentId);
    setInputText("");
  };

  const handleSubmitQuestion = () => {
    if (!questionText.trim()) return;
    onSubmitQuestion(questionText.trim());
    setQuestionText("");
  };

  // Question mode (CHECK_UNDERSTANDING active)
  if (currentQuestion) {
    const visibleHints = currentQuestion.hints.slice(
      0,
      currentQuestion.hintsShown
    );
    const hasMoreHints =
      currentQuestion.hintsShown < currentQuestion.hints.length;

    return (
      <div className="p-4 bg-[#161b22] border-t border-[#30363d]">
        <div className="flex items-start gap-3 mb-3">
          <span className="material-symbols-rounded text-yellow-500 text-xl">
            help
          </span>
          <div>
            <p className="text-sm font-medium text-white">
              {currentQuestion.question}
            </p>
            <span className="text-xs text-[#8b949e]">
              {currentQuestion.questionType}
            </span>
          </div>
        </div>

        {/* Visible hints */}
        {visibleHints.length > 0 && (
          <div className="mb-3 space-y-1">
            {visibleHints.map((hint, i) => (
              <div
                key={i}
                className="flex items-start gap-2 text-xs text-[#8b949e] bg-[#21262d] px-3 py-2 rounded"
              >
                <span className="material-symbols-rounded text-sm text-yellow-600">
                  lightbulb
                </span>
                {hint}
              </div>
            ))}
          </div>
        )}

        {/* Answer input */}
        <div className="flex gap-2">
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmitResponse()}
            placeholder="Type your answer..."
            className="flex-1 bg-[#21262d] border border-[#30363d] rounded-lg px-3 py-2 text-sm text-white placeholder-[#8b949e] focus:outline-none focus:border-[#0d968b]"
          />
          <button
            onClick={handleSubmitResponse}
            disabled={!inputText.trim()}
            className="px-4 py-2 bg-[#0d968b] text-white text-sm rounded-lg hover:bg-[#0b8278] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Submit
          </button>
          {hasMoreHints && (
            <button
              onClick={showNextHint}
              className="px-3 py-2 bg-[#21262d] text-[#8b949e] text-sm rounded-lg hover:bg-[#30363d] transition-colors"
              title="Show hint"
            >
              <span className="material-symbols-rounded text-sm">
                lightbulb
              </span>
            </button>
          )}
        </div>
      </div>
    );
  }

  // Raised hand mode (student asking a question)
  if (isHandRaised) {
    return (
      <div className="p-4 bg-[#161b22] border-t border-[#30363d]">
        <div className="flex items-center gap-2 mb-2">
          <span className="material-symbols-rounded text-yellow-500">
            front_hand
          </span>
          <span className="text-sm text-white">
            Hand raised — type your question
          </span>
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={questionText}
            onChange={(e) => setQuestionText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmitQuestion()}
            placeholder="Ask your question..."
            className="flex-1 bg-[#21262d] border border-[#30363d] rounded-lg px-3 py-2 text-sm text-white placeholder-[#8b949e] focus:outline-none focus:border-[#0d968b]"
            autoFocus
          />
          <button
            onClick={handleSubmitQuestion}
            disabled={!questionText.trim()}
            className="px-4 py-2 bg-[#0d968b] text-white text-sm rounded-lg hover:bg-[#0b8278] disabled:opacity-50 transition-colors"
          >
            Ask
          </button>
        </div>
      </div>
    );
  }

  // Waiting state
  if (isWaiting && waitReason === "thinking_time") {
    return (
      <div className="p-4 bg-[#161b22] border-t border-[#30363d]">
        <div className="flex items-center gap-2 text-[#8b949e]">
          <div className="w-4 h-4 border-2 border-[#0d968b] border-t-transparent rounded-full animate-spin" />
          <span className="text-sm">
            Take a moment to think about this...
          </span>
        </div>
      </div>
    );
  }

  // Default: dialogue history
  return (
    <div className="p-4 bg-[#161b22] border-t border-[#30363d] max-h-[200px] overflow-y-auto">
      {status === "completed" ? (
        <div className="flex items-center gap-2 text-[#0d968b]">
          <span className="material-symbols-rounded">check_circle</span>
          <span className="text-sm font-medium">Lesson complete!</span>
        </div>
      ) : dialogueHistory.length > 0 ? (
        <div className="space-y-2">
          {dialogueHistory.slice(-5).map((entry, i) => (
            <div key={i} className="flex items-start gap-2">
              <span
                className={`material-symbols-rounded text-sm mt-0.5 ${
                  entry.role === "teacher"
                    ? "text-[#0d968b]"
                    : "text-blue-400"
                }`}
              >
                {entry.role === "teacher" ? "record_voice_over" : "person"}
              </span>
              <p className="text-xs text-[#c9d1d9] leading-relaxed">
                {entry.text}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-[#8b949e]">
          Lesson starting...
        </p>
      )}
    </div>
  );
}
