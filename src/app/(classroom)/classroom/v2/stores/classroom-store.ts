import { create } from "zustand";

// Frame-based (not segment-based)
export interface FrameInfo {
  id: string;
  url: string;
  index: number;
  totalFrames: number;
  progressPct: number;
}

export interface QuestionData {
  question: string;
  questionType: string;
  hints: string[];
  frameId: string;
  hintsShown: number;
}

export interface DialogueEntry {
  role: "teacher" | "student";
  text: string;
  time: string;
}

interface ClassroomState {
  // Session
  sessionId: string;
  roomCode: string;
  lessonTitle: string;
  status:
    | "connecting"
    | "preparing"
    | "starting"
    | "active"
    | "paused"
    | "completed"
    | "error";
  errorMessage: string;

  // Frame (replaces segment)
  currentFrame: FrameInfo | null;
  currentStep: string;
  frameTitle: string;
  fallbackDescription: string;

  iframeReady: boolean;
  iframeLabels: string[];

  // Teacher
  teacherSpeech: string;
  isSpeaking: boolean;
  speechType: string;

  // Student interaction
  currentQuestion: QuestionData | null;
  isHandRaised: boolean;
  isChatOpen: boolean;
  isMicOn: boolean;

  // Chat history
  messages: DialogueEntry[];

  // Timing
  elapsedSeconds: number;

  // Session summary (when completed)
  summary: Record<string, unknown> | null;

  // Actions
  setSessionInfo: (info: {
    sessionId: string;
    lessonTitle: string;
    totalFrames: number;
    isResuming: boolean;
  }) => void;
  setStatus: (status: ClassroomState["status"]) => void;
  setCurrentFrame: (frame: FrameInfo | null) => void;
  setCurrentStep: (step: string) => void;
  setFrameTitle: (title: string) => void;
  setFallbackDescription: (desc: string) => void;
  setIframeReady: (ready: boolean) => void;
  setIframeLabels: (labels: string[]) => void;
  setTeacherSpeech: (text: string, speechType?: string) => void;
  clearTeacherSpeech: () => void;
  setIsSpeaking: (speaking: boolean) => void;
  setCurrentQuestion: (q: QuestionData | null) => void;
  showNextHint: () => void;
  toggleHandRaised: () => void;
  toggleChat: () => void;
  toggleMic: () => void;
  addMessage: (entry: DialogueEntry) => void;
  setSummary: (summary: Record<string, unknown>) => void;
  incrementTimer: () => void;
  setError: (message: string) => void;
  reset: () => void;
}

const initialState = {
  sessionId: "",
  roomCode: "",
  lessonTitle: "",
  status: "connecting" as const,
  errorMessage: "",

  currentFrame: null,
  currentStep: "",
  frameTitle: "",
  fallbackDescription: "",
  iframeReady: false,
  iframeLabels: [] as string[],

  teacherSpeech: "",
  isSpeaking: false,
  speechType: "",

  currentQuestion: null,
  isHandRaised: false,
  isChatOpen: false,
  isMicOn: false,

  messages: [] as DialogueEntry[],

  elapsedSeconds: 0,

  summary: null,
};

export const useClassroomStore = create<ClassroomState>((set) => ({
  ...initialState,

  // Actions
  setSessionInfo: (info) =>
    set({
      sessionId: info.sessionId,
      lessonTitle: info.lessonTitle,
      status: info.isResuming ? "active" : "starting",
    }),

  setStatus: (status) => set({ status }),

  setCurrentFrame: (frame) => set({ currentFrame: frame }),

  setCurrentStep: (step) => set({ currentStep: step }),

  setFrameTitle: (title) => set({ frameTitle: title }),

  setFallbackDescription: (desc) => set({ fallbackDescription: desc }),

  setIframeReady: (ready) => set({ iframeReady: ready }),

  setIframeLabels: (labels) => set({ iframeLabels: labels }),

  setTeacherSpeech: (text, speechType = "narration") =>
    set({ teacherSpeech: text, speechType }),

  clearTeacherSpeech: () =>
    set({ teacherSpeech: "", speechType: "", isSpeaking: false }),

  setIsSpeaking: (speaking) => set({ isSpeaking: speaking }),

  setCurrentQuestion: (q) => set({ currentQuestion: q }),

  showNextHint: () =>
    set((state) => {
      if (!state.currentQuestion) return {};
      return {
        currentQuestion: {
          ...state.currentQuestion,
          hintsShown: state.currentQuestion.hintsShown + 1,
        },
      };
    }),

  toggleHandRaised: () =>
    set((state) => ({ isHandRaised: !state.isHandRaised })),

  toggleChat: () => set((state) => ({ isChatOpen: !state.isChatOpen })),

  toggleMic: () => set((state) => ({ isMicOn: !state.isMicOn })),

  addMessage: (entry) =>
    set((state) => ({
      messages: [...state.messages.slice(-99), entry],
    })),

  setSummary: (summary) =>
    set({ summary, status: "completed" }),

  incrementTimer: () =>
    set((state) => ({ elapsedSeconds: state.elapsedSeconds + 1 })),

  setError: (message) => set({ errorMessage: message, status: "error" }),

  reset: () => set({ ...initialState }),
}));
