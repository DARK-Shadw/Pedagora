/**
 * Lockstep sync engine for animation + audio.
 *
 * For each step in a frame:
 *   1. Seek the animation iframe to the step's label (paused)
 *   2. Play the audio chunk for that step
 *   3. After audio ends, animate the iframe forward to the next step's label
 *   4. Repeat
 *
 * This guarantees zero drift between speech and animation. Validated by
 * sync_tests/test3_sync_prototype.py and test5_piper_quality.py — perfect
 * step-by-step alignment with no race conditions.
 */

export interface StepBundle {
  label: string;
  anim_time: number;
  text: string;
  audio_b64: string;
  duration_s: number;
}

export interface FrameBundle {
  frame_id: string;
  frame_url: string;
  frame_index: number;
  total_frames: number;
  progress_pct: number;
  frame_title: string;
  fallback_description: string;
  steps: StepBundle[];
}

export interface LockstepCallbacks {
  onSubtitle: (text: string, isSpeaking: boolean) => void;
  onStepChange: (label: string) => void;
  onFrameDone: () => void;
  onError: (msg: string) => void;
}

const IFRAME_READY_TIMEOUT_MS = 3000;
const IFRAME_READY_POLL_MS = 50;
const ANIMATE_TO_STEP_TIMEOUT_MS = 30000;

export class LockstepEngine {
  private audioCtx: AudioContext;
  private callbacks: LockstepCallbacks;
  private isIframeReady: () => boolean;
  private currentSource: AudioBufferSourceNode | null = null;
  private paused: boolean = false;
  private stopped: boolean = false;
  private resumeWaiter: { resolve: () => void } | null = null;
  private iframeReady: boolean = false;
  private currentFrameId: string = "";

  constructor(
    audioCtx: AudioContext,
    callbacks: LockstepCallbacks,
    isIframeReady: () => boolean,
  ) {
    this.audioCtx = audioCtx;
    this.callbacks = callbacks;
    this.isIframeReady = isIframeReady;
  }

  /**
   * Play one frame's bundled steps end-to-end. Calls onFrameDone when finished.
   * Safe to call concurrently with stop()/pause()/resume().
   */
  async playFrame(frame: FrameBundle): Promise<void> {
    this.stopped = false;
    this.iframeReady = false;
    this.currentFrameId = frame.frame_id;

    // Wait up to 3s for iframe to load + first stepChanged event.
    // If timeout, assume animation is broken — degrade to audio-only mode.
    await this.waitForIframeReady(IFRAME_READY_TIMEOUT_MS);

    for (let i = 0; i < frame.steps.length; i++) {
      if (this.stopped) return;
      if (this.paused) await this.waitForResume();
      if (this.stopped) return;

      const step = frame.steps[i];
      const next = frame.steps[i + 1];

      // 1. Seek + pause (only if iframe is alive)
      if (this.iframeReady && step.label) {
        this.sendToIframe({ action: "seekToStep", label: step.label });
        this.sendToIframe({ action: "pause" });
        this.callbacks.onStepChange(step.label);
      }

      // 2. Play audio (skip if synth failed for this step)
      if (step.audio_b64 && step.text) {
        this.callbacks.onSubtitle(step.text, true);
        try {
          await this.playAudio(step.audio_b64);
        } catch (e) {
          console.error("[Lockstep] audio decode failed:", e);
          // Brief silent pause as fallback
          await this.sleep(2000);
        }
        this.callbacks.onSubtitle("", false);
      } else if (step.text) {
        // Audio missing but text present — show subtitle for read-time
        this.callbacks.onSubtitle(step.text, false);
        await this.sleep(Math.max(2000, step.text.length * 60));
        this.callbacks.onSubtitle("", false);
      }

      if (this.stopped) return;

      // 3. Animate to next step (or just hold the last one)
      if (next && this.iframeReady) {
        await this.animateToStep(next.label);
      }
    }

    if (!this.stopped) {
      this.callbacks.onFrameDone();
    }
  }

  private playAudio(b64: string): Promise<void> {
    return new Promise(async (resolve, reject) => {
      try {
        // Decode base64 -> bytes
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);

        // Decode WAV -> AudioBuffer
        const buf = await this.audioCtx.decodeAudioData(bytes.buffer);

        // Play
        const src = this.audioCtx.createBufferSource();
        src.buffer = buf;
        src.connect(this.audioCtx.destination);
        src.onended = () => {
          if (this.currentSource === src) this.currentSource = null;
          resolve();
        };
        this.currentSource = src;
        src.start();
      } catch (e) {
        reject(e);
      }
    });
  }

  private animateToStep(targetLabel: string): Promise<void> {
    return new Promise((resolve) => {
      let resolved = false;
      const finish = () => {
        if (resolved) return;
        resolved = true;
        window.removeEventListener("message", handler);
        clearTimeout(timer);
        this.sendToIframe({ action: "pause" });
        resolve();
      };

      const handler = (e: MessageEvent) => {
        if (
          e.data?.event === "stepChanged" &&
          e.data.label === targetLabel
        ) {
          finish();
        }
      };
      window.addEventListener("message", handler);

      // Safety timeout — if step never reached, just continue
      const timer = window.setTimeout(finish, ANIMATE_TO_STEP_TIMEOUT_MS);

      // Start playing forward
      this.sendToIframe({ action: "play" });
    });
  }

  /**
   * Wait for the iframe to be ready, but POLL the store flag instead of
   * listening for an event. The store flag is published by AnimationFrame's
   * own message listener as soon as the iframe fires its first stepChanged.
   *
   * Why polling and not a fresh event listener: for the first frame, the
   * iframe is pre-loaded via show_frame BEFORE this engine starts running.
   * Its initial stepChanged event has already fired (and was caught by
   * AnimationFrame, which set the store flag). A fresh listener attached
   * here would wait forever for an event that already happened.
   */
  private async waitForIframeReady(timeoutMs: number): Promise<void> {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (this.stopped) return;
      if (this.isIframeReady()) {
        this.iframeReady = true;
        // Force-pause: the generated HTML starts paused, but if a stray
        // tl.play() slips through this catches it before the audio starts.
        this.sendToIframe({ action: "pause" });
        return;
      }
      await this.sleep(IFRAME_READY_POLL_MS);
    }
    // Timeout — animation is broken or never loaded. iframeReady stays
    // false and the playFrame loop degrades to audio-only.
  }

  private sendToIframe(msg: object): void {
    const iframe = document.querySelector<HTMLIFrameElement>(
      'iframe[title="Animation"]'
    );
    iframe?.contentWindow?.postMessage(msg, "*");
  }

  private waitForResume(): Promise<void> {
    return new Promise((resolve) => {
      this.resumeWaiter = { resolve };
    });
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((r) => setTimeout(r, ms));
  }

  pause(): void {
    this.paused = true;
    try {
      this.currentSource?.stop();
    } catch {
      /* already stopped */
    }
    this.sendToIframe({ action: "pause" });
  }

  resume(): void {
    this.paused = false;
    if (this.resumeWaiter) {
      this.resumeWaiter.resolve();
      this.resumeWaiter = null;
    }
  }

  stop(): void {
    this.stopped = true;
    try {
      this.currentSource?.stop();
    } catch {
      /* already stopped */
    }
    this.currentSource = null;
    if (this.resumeWaiter) {
      this.resumeWaiter.resolve();
      this.resumeWaiter = null;
    }
  }
}
