import { create } from "zustand";

export interface TeacherSpeech {
  text: string;
  type: string;
  segmentId: string;
}

export interface AnimationCommand {
  animationId: string;
  url: string;
  action: "play" | "pause" | "rewind";
  durationSeconds: number;
}

export interface QuestionData {
  question: string;
  questionType: string;
  hints: string[];
  segmentId: string;
  hintsShown: number;
}

export interface SegmentInfo {
  id: string;
  type: string;
  title: string;
  progressPct: number;
}

export interface DialogueEntry {
  role: "teacher" | "student";
  text: string;
  timestamp: string;
}

interface ClassroomState {
  // Connection
  sessionId: string;
  lessonTitle: string;
  status: "connecting" | "active" | "paused" | "completed" | "error";
  isResuming: boolean;
  totalSegments: number;
  errorMessage: string;

  // Teaching state
  currentSegment: SegmentInfo | null;
  teacherSpeech: TeacherSpeech | null;
  isSpeaking: boolean;
  currentAnimation: AnimationCommand | null;
  currentQuestion: QuestionData | null;
  isWaiting: boolean;
  waitReason: string;

  // Student state
  isHandRaised: boolean;
  studentResponse: string;
  isListening: boolean; // STT active

  // Session data
  dialogueHistory: DialogueEntry[];
  sessionSummary: Record<string, unknown> | null;
  elapsedSeconds: number;

  // Actions
  setSessionInfo: (info: {
    sessionId: string;
    lessonTitle: string;
    totalSegments: number;
    isResuming: boolean;
  }) => void;
  setStatus: (status: ClassroomState["status"]) => void;
  setTeacherSpeech: (speech: TeacherSpeech | null) => void;
  setIsSpeaking: (speaking: boolean) => void;
  setCurrentAnimation: (anim: AnimationCommand | null) => void;
  setCurrentQuestion: (q: QuestionData | null) => void;
  showNextHint: () => void;
  setCurrentSegment: (seg: SegmentInfo | null) => void;
  setIsWaiting: (waiting: boolean, reason?: string) => void;
  toggleHandRaised: () => void;
  setStudentResponse: (text: string) => void;
  setIsListening: (listening: boolean) => void;
  addDialogue: (entry: DialogueEntry) => void;
  setSessionSummary: (summary: Record<string, unknown>) => void;
  incrementTimer: () => void;
  setError: (message: string) => void;
  reset: () => void;
}

export const useClassroomStore = create<ClassroomState>((set) => ({
  // Initial state
  sessionId: "",
  lessonTitle: "",
  status: "connecting",
  isResuming: false,
  totalSegments: 0,
  errorMessage: "",

  currentSegment: null,
  teacherSpeech: null,
  isSpeaking: false,
  currentAnimation: null,
  currentQuestion: null,
  isWaiting: false,
  waitReason: "",

  isHandRaised: false,
  studentResponse: "",
  isListening: false,

  dialogueHistory: [],
  sessionSummary: null,
  elapsedSeconds: 0,

  // Actions
  setSessionInfo: (info) =>
    set({
      sessionId: info.sessionId,
      lessonTitle: info.lessonTitle,
      totalSegments: info.totalSegments,
      isResuming: info.isResuming,
      status: "active",
    }),

  setStatus: (status) => set({ status }),

  setTeacherSpeech: (speech) => set({ teacherSpeech: speech }),

  setIsSpeaking: (speaking) => set({ isSpeaking: speaking }),

  setCurrentAnimation: (anim) => set({ currentAnimation: anim }),

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

  setCurrentSegment: (seg) => set({ currentSegment: seg }),

  setIsWaiting: (waiting, reason = "") =>
    set({ isWaiting: waiting, waitReason: reason }),

  toggleHandRaised: () =>
    set((state) => ({ isHandRaised: !state.isHandRaised })),

  setStudentResponse: (text) => set({ studentResponse: text }),

  setIsListening: (listening) => set({ isListening: listening }),

  addDialogue: (entry) =>
    set((state) => ({
      dialogueHistory: [...state.dialogueHistory.slice(-50), entry],
    })),

  setSessionSummary: (summary) =>
    set({ sessionSummary: summary, status: "completed" }),

  incrementTimer: () =>
    set((state) => ({ elapsedSeconds: state.elapsedSeconds + 1 })),

  setError: (message) => set({ errorMessage: message, status: "error" }),

  reset: () =>
    set({
      sessionId: "",
      lessonTitle: "",
      status: "connecting",
      isResuming: false,
      totalSegments: 0,
      errorMessage: "",
      currentSegment: null,
      teacherSpeech: null,
      isSpeaking: false,
      currentAnimation: null,
      currentQuestion: null,
      isWaiting: false,
      waitReason: "",
      isHandRaised: false,
      studentResponse: "",
      isListening: false,
      dialogueHistory: [],
      sessionSummary: null,
      elapsedSeconds: 0,
    }),
}));
