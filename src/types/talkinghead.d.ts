declare module "@met4citizen/talkinghead" {
  export class TalkingHead {
    constructor(node: HTMLElement, opt?: Record<string, unknown>);

    showAvatar(
      avatar: {
        url: string;
        body?: "M" | "F";
        avatarMood?: string;
        lipsyncLang?: string;
        ttsLang?: string;
        ttsVoice?: string;
        [key: string]: unknown;
      },
      onprogress?: (url: string, event: ProgressEvent) => void
    ): Promise<void>;

    speakAudio(
      audio: {
        audio: ArrayBuffer | ArrayBuffer[];
        words?: string[];
        wtimes?: number[];
        wdurations?: number[];
        visemes?: string[];
        vtimes?: number[];
        vdurations?: number[];
        [key: string]: unknown;
      },
      opt?: Record<string, unknown>,
      onsubtitles?: (node: HTMLElement) => void
    ): void;

    speakText(
      text: string,
      opt?: Record<string, unknown>,
      onsubtitles?: (node: HTMLElement) => void,
      excludes?: string[]
    ): void;

    setMood(mood: string): void;
    setView(view: string, opt?: Record<string, unknown>): void;
    lookAt(x: number, y: number, t: number): void;
    lookAtCamera(t: number): void;
    start(): void;
    stop(): void;
    playAnimation(
      url: string,
      onprogress?: (event: ProgressEvent) => void,
      dur?: number,
      ndx?: number,
      scale?: number
    ): void;
    playGesture(name: string, dur?: number, mirror?: boolean, ms?: number): void;

    readonly isSpeaking: boolean;
    readonly isAudioPlaying: boolean;

    onstartspeaking: (() => void) | null;
    onendspeaking: (() => void) | null;
  }
}
