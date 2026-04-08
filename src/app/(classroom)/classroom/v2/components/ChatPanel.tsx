"use client";

import { memo, useEffect, useRef, useState } from "react";

interface DialogueEntry {
  role: "teacher" | "student";
  text: string;
  time: string;
}

interface ChatPanelProps {
  isOpen: boolean;
  messages: DialogueEntry[];
  onSendMessage: (text: string) => void;
  onClose: () => void;
}

/**
 * Sliding chat panel from the right edge.
 * Shows dialogue history + input for student messages.
 */
function ChatPanelInner({ isOpen, messages, onSendMessage, onClose }: ChatPanelProps) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.length]);

  function handleSend() {
    if (!input.trim()) return;
    onSendMessage(input.trim());
    setInput("");
  }

  return (
    <div
      className={`
        absolute top-0 right-0 bottom-0 z-20
        w-[340px] max-w-[85vw]
        bg-[#0d1117]/95 backdrop-blur-lg border-l border-white/5
        flex flex-col
        transition-transform duration-300 ease-out
        ${isOpen ? "translate-x-0" : "translate-x-full"}
      `}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <span className="text-white/80 text-sm font-medium">Chat</span>
        <button
          onClick={onClose}
          className="text-white/40 hover:text-white/80 transition-colors"
        >
          <span className="material-symbols-rounded text-[20px]">close</span>
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <p className="text-white/20 text-sm text-center mt-8">
            Chat messages will appear here
          </p>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex flex-col ${msg.role === "student" ? "items-end" : "items-start"}`}
          >
            <div
              className={`
                max-w-[85%] px-3 py-2 rounded-xl text-sm leading-relaxed
                ${msg.role === "student"
                  ? "bg-[#0d968b]/20 text-white/90"
                  : "bg-white/5 text-white/70"
                }
              `}
            >
              {msg.text}
            </div>
            <span className="text-white/20 text-[10px] mt-0.5 px-1">
              {msg.role === "teacher" ? "Teacher" : "You"} · {msg.time}
            </span>
          </div>
        ))}
      </div>

      {/* Input */}
      <div className="p-3 border-t border-white/5">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Type a message..."
            className="flex-1 px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm placeholder:text-white/20 focus:outline-none focus:border-[#0d968b]/40"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="px-3 py-2 bg-[#0d968b] hover:bg-[#0ba898] disabled:opacity-30 text-white rounded-lg transition-colors"
          >
            <span className="material-symbols-rounded text-[18px]">send</span>
          </button>
        </div>
      </div>
    </div>
  );
}

export const ChatPanel = memo(ChatPanelInner);
