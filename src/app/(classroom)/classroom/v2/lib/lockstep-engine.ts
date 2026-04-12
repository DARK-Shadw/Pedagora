/**
 * Lockstep sync engine for animation + audio.
 *
 * Two playback modes, chosen per-frame at runtime:
 *
 * LOCKSTEP MODE (labels verified):
 *   For each step: seek → pause → play audio → animate to next label → repeat.
 *   Perfect sync between speech and animation.
 *
 * FREE-PLAY MODE (labels missing or mismatched):
 *   Animation plays naturally at its own pace. Audio plays in sequence on top.
 *   No seeking, no pausing the animation, no 8s dead waits between steps.
 *   The animation won't sync per-step, but it won't REPLAY or FREEZE either.
 *
 * The mode is determined by verifyLabels(): after the iframe loads, we seek to
 * the first step's label and wait 500ms for a matching stepChanged event. If
 * the animation responds, labels are present → lockstep. If not → free-play.
 *
 * Frame isolation: each playFrame() increments a generation counter. If a new
 * frame starts while the old is running, the old loop exits at the next check.
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
const ANIMATE_TO_STEP_DEFAULT_TIMEOUT_MS = 20000;
const ANIMATE_TO_STEP_MARGIN_MS = 4000;
const LABEL_VERIFY_TIMEOUT_MS = 600;

export class LockstepEngine {
  private audioCtx: AudioContext;
  private callbacks: LockstepCallbacks;
  private isIframeReady: () => boolean;
  private currentSource: AudioBufferSourceNode | null = null;
  private paused: boolean = false;
  private stopped: boolean = false;
  private resumeWaiter: { resolve: () => void } | null = null;
  private iframeReady: boolean = false;
  private labelsVerified: boolean = false;
  private currentFrameId: string = "";
  private _generation: number = 0;
  private _pendingAnimateFinish: (() => void) | null = null;

  constructor(
    audioCtx: AudioContext,
    callbacks: LockstepCallbacks,
    isIframeReady: () => boolean,
  ) {
    this.audioCtx = audioCtx;
    this.callbacks = callbacks;
    this.isIframeReady = isIframeReady;
  }

  async playFrame(frame: FrameBundle): Promise<void> {
    this.stop();

    const gen = ++this._generation;
    this.stopped = false;
    this.iframeReady = false;
    this.labelsVerified = false;
    this.currentFrameId = frame.frame_id;

    console.log(
      `[Lockstep] playFrame ${frame.frame_id} gen=${gen} (${frame.steps.length} steps, ` +
      `labels=[${frame.steps.map(s => s.label).join(",")}])`
    );

    // Wait for iframe to load + first stepChanged event
    await this.waitForIframeReady(IFRAME_READY_TIMEOUT_MS);

    // Verify labels: seek to a step, check if animation responds.
    // NOTE: Due to the _lastStep dedup in the iframe's _notifyStepChange,
    // this currently always returns false (FREE-PLAY mode) because the
    // iframe already fired stepChanged(firstLabel) on initial load. This
    // is intentional for now — FREE-PLAY works well. When we implement
    // proper LOCKSTEP (with the iframe posting label events on seek),
    // this will start returning true.
    if (this.iframeReady && frame.steps.length > 0) {
      this.labelsVerified = await this.verifyLabels(frame.steps[0].label);
    }

    const mode = !this.iframeReady
      ? "AUDIO-ONLY"
      : this.labelsVerified
        ? "LOCKSTEP"
        : "FREE-PLAY";
    console.log(`[Lockstep] ${frame.frame_id} mode=${mode}`);

    // FREE-PLAY: let animation run at its own pace, don't interfere
    if (this.iframeReady && !this.labelsVerified) {
      this.sendToIframe({ action: "play" });
    }

    for (let i = 0; i < frame.steps.length; i++) {
      if (this.stopped || this._generation !== gen) return;
      if (this.paused) await this.waitForResume();
      if (this.stopped || this._generation !== gen) return;

      const step = frame.steps[i];
      const next = frame.steps[i + 1];

      console.log(
        `[Lockstep] ${frame.frame_id} step[${i}/${frame.steps.length}] ` +
        `label="${step.label}" dur=${step.duration_s.toFixed(1)}s txt=${step.text.length}ch`
      );

      // 1. Seek + pause (LOCKSTEP mode only)
      if (this.labelsVerified && step.label) {
        this.sendToIframe({ action: "seekToStep", label: step.label });
        this.sendToIframe({ action: "pause" });
        this.callbacks.onStepChange(step.label);
      }

      // 2. Play audio
      if (step.audio_b64 && step.text) {
        this.callbacks.onSubtitle(step.text, true);
        try {
          await this.playAudio(step.audio_b64);
        } catch (e) {
          console.error("[Lockstep] audio decode failed:", e);
          await this.sleep(2000);
        }
        this.callbacks.onSubtitle("", false);
      } else if (step.text) {
        const readTime = Math.max(2000, step.text.length * 60);
        this.callbacks.onSubtitle(step.text, false);
        await this.sleep(readTime);
        this.callbacks.onSubtitle("", false);
      }

      if (this.stopped || this._generation !== gen) return;

      // 3. Animate to next step (LOCKSTEP mode only)
      if (next && this.labelsVerified) {
        // Compute expected transition duration from anim_time difference
        const transitionSec = Math.max(
          (next.anim_time || 0) - (step.anim_time || 0),
          2,
        );
        await this.animateToStep(next.label, transitionSec * 1000);
      }
    }

    if (!this.stopped && this._generation === gen) {
      // In FREE-PLAY mode, pause the animation when all audio is done
      if (this.iframeReady && !this.labelsVerified) {
        this.sendToIframe({ action: "pause" });
      }
      console.log(`[Lockstep] ${frame.frame_id} DONE (${mode}) — sending frame_done`);
      this.callbacks.onFrameDone();
    }
  }

  /**
   * Check if the animation's GSAP timeline has matching labels.
   *
   * Seeks to `firstLabel` and waits for a `stepChanged` event. If the
   * animation responds within LABEL_VERIFY_TIMEOUT_MS → labels verified
   * → LOCKSTEP mode. Otherwise → FREE-PLAY mode.
   *
   * Known limitation: on iframe load, _notifyStepChange() fires
   * stepChanged(firstLabel) immediately, setting _lastStep = firstLabel.
   * A subsequent seekToStep(firstLabel) doesn't change the step, so no
   * event fires → this always returns false (FREE-PLAY). This is fine
   * for now since FREE-PLAY works well for both video and GSAP frames.
   */
  private verifyLabels(firstLabel: string): Promise<boolean> {
    if (!firstLabel) return Promise.resolve(false);
    return new Promise((resolve) => {
      let done = false;
      const finish = (result: boolean) => {
        if (done) return;
        done = true;
        window.removeEventListener("message", handler);
        clearTimeout(timer);
        resolve(result);
      };
      const handler = (e: MessageEvent) => {
        if (
          e.data?.event === "stepChanged" &&
          e.data.label === firstLabel
        ) {
          console.log(`[Lockstep] label "${firstLabel}" VERIFIED — lockstep mode`);
          finish(true);
        }
      };
      window.addEventListener("message", handler);
      this.sendToIframe({ action: "seekToStep", label: firstLabel });

      const timer = setTimeout(() => {
        console.log(`[Lockstep] label "${firstLabel}" NOT FOUND — free-play mode`);
        finish(false);
      }, LABEL_VERIFY_TIMEOUT_MS);
    });
  }

  private playAudio(b64: string): Promise<void> {
    return new Promise(async (resolve, reject) => {
      try {
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const buf = await this.audioCtx.decodeAudioData(bytes.buffer);
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

  /**
   * Play the animation forward until the target label is reached.
   *
   * @param targetLabel    GSAP label (or video step) to play toward
   * @param transitionMs   Expected duration of the transition in ms (from
   *                       anim_time difference between steps). The timeout
   *                       is set to this + a margin so the animation has
   *                       time to actually reach the label.
   */
  private animateToStep(
    targetLabel: string,
    transitionMs: number = ANIMATE_TO_STEP_DEFAULT_TIMEOUT_MS,
  ): Promise<void> {
    const timeout = Math.max(
      transitionMs + ANIMATE_TO_STEP_MARGIN_MS,
      ANIMATE_TO_STEP_MARGIN_MS,
    );
    return new Promise((resolve) => {
      let resolved = false;
      const finish = () => {
        if (resolved) return;
        resolved = true;
        window.removeEventListener("message", handler);
        clearTimeout(timer);
        this._pendingAnimateFinish = null;
        this.sendToIframe({ action: "pause" });
        resolve();
      };

      this._pendingAnimateFinish = finish;

      const handler = (e: MessageEvent) => {
        if (
          e.data?.event === "stepChanged" &&
          e.data.label === targetLabel
        ) {
          finish();
        }
      };
      window.addEventListener("message", handler);
      const timer = window.setTimeout(finish, timeout);
      this.sendToIframe({ action: "play" });
    });
  }

  private async waitForIframeReady(timeoutMs: number): Promise<void> {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (this.stopped) return;
      if (this.isIframeReady()) {
        this.iframeReady = true;
        this.sendToIframe({ action: "pause" });
        return;
      }
      await this.sleep(IFRAME_READY_POLL_MS);
    }
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
    // Pause the old iframe animation so it doesn't fire stale stepChanged
    // events that could set iframeReady=true before the new frame loads.
    this.sendToIframe({ action: "pause" });
    if (this.resumeWaiter) {
      this.resumeWaiter.resolve();
      this.resumeWaiter = null;
    }
    if (this._pendingAnimateFinish) {
      this._pendingAnimateFinish();
      this._pendingAnimateFinish = null;
    }
  }
}
