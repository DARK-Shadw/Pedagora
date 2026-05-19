/**
 * Lockstep sync engine — audio + animation sync (stage 4, frontend).
 * See docs/architecture-flow.svg for where this fits in the pipeline.
 *
 * Receives FrameBundle from backend via WebSocket and orchestrates
 * audio playback + GSAP animation seeking in perfect sync.
 *
 * Three playback modes, chosen per-frame at runtime:
 *
 * LOCKSTEP MODE (labels verified):
 *   For each step: seek → pause → play audio → animate to next label → repeat.
 *   Perfect sync between speech and animation.
 *
 * FREE-PLAY MODE (iframe ready but labels don't match):
 *   Animation plays naturally at its own pace. Audio plays in sequence on top.
 *   No seeking, no pausing the animation.
 *
 * AUDIO-ONLY MODE (iframe not ready — broken or slow-loading):
 *   Only audio plays. No animation commands sent.
 *
 * Label verification: the iframe posts an `iframeReady` event with its GSAP
 * labels. If the bundle's step labels are a subset → LOCKSTEP. For older
 * frames without the iframeReady event, we send a `queryLabels` command and
 * wait for a `labelsResponse`. If neither works → FREE-PLAY or AUDIO-ONLY.
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

const IFRAME_READY_TIMEOUT_MS = 10000;
const IFRAME_READY_POLL_MS = 50;
const ANIMATE_TO_STEP_DEFAULT_TIMEOUT_MS = 20000;
const ANIMATE_TO_STEP_MARGIN_MS = 4000;
const QUERY_LABELS_TIMEOUT_MS = 1500;

export class LockstepEngine {
  private audioCtx: AudioContext;
  private callbacks: LockstepCallbacks;
  private isIframeReady: () => boolean;
  private getIframeLabels: () => string[];
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
    getIframeLabels: () => string[],
  ) {
    this.audioCtx = audioCtx;
    this.callbacks = callbacks;
    this.isIframeReady = isIframeReady;
    this.getIframeLabels = getIframeLabels;
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

    // Wait for iframe to load and report ready
    await this.waitForIframeReady(IFRAME_READY_TIMEOUT_MS);

    // Check if the bundle's step labels exist in the iframe's reported labels
    if (this.iframeReady && frame.steps.length > 0) {
      this.labelsVerified = await this.checkLabels(frame);
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
        const transitionSec = Math.max(
          (next.anim_time || 0) - (step.anim_time || 0),
          2,
        );
        await this.animateToStep(next.label, transitionSec * 1000);
      }
    }

    if (!this.stopped && this._generation === gen) {
      if (this.iframeReady && !this.labelsVerified) {
        this.sendToIframe({ action: "pause" });
      }
      console.log(`[Lockstep] ${frame.frame_id} DONE (${mode}) — sending frame_done`);
      this.callbacks.onFrameDone();
    }
  }

  /**
   * Check if the iframe's GSAP labels match the bundle's step labels.
   *
   * Strategy:
   * 1. Check labels from the store (set by iframeReady event from new templates)
   * 2. If empty, send queryLabels command and wait for labelsResponse (new templates)
   * 3. If still empty, fall back to seek-based verification (old templates)
   *
   * When names differ but counts match, remap bundle labels to iframe labels
   * by position (Nth storyboard step → Nth GSAP label). This handles the
   * common case where the LLM used different label names than the planner.
   */
  private async checkLabels(frame: FrameBundle): Promise<boolean> {
    const bundleLabels = frame.steps.map(s => s.label).filter(Boolean);
    if (bundleLabels.length === 0) return false;

    // Strategy 1: labels already in store from iframeReady event
    let iframeLabels = this.getIframeLabels();

    // Strategy 2: send queryLabels and wait for response
    if (iframeLabels.length === 0) {
      iframeLabels = await this.queryLabelsFromIframe();
    }

    // Strategy 3: seek-based fallback for old templates
    if (iframeLabels.length === 0) {
      const verified = await this.verifyLabelBySeek(bundleLabels[0]);
      if (verified) {
        console.log(`[Lockstep] labels verified via seek fallback`);
      }
      return verified;
    }

    // Exact match — all bundle labels exist in iframe
    const iframeLabelSet = new Set(iframeLabels);
    const allMatch = bundleLabels.every(l => iframeLabelSet.has(l));
    if (allMatch) {
      console.log(
        `[Lockstep] all ${bundleLabels.length} labels match exactly ` +
        `(iframe has ${iframeLabels.length} total)`
      );
      return true;
    }

    // Position-based remap: bundle has N steps, iframe has >= N labels.
    // Assume the Nth storyboard step corresponds to the Nth GSAP label.
    if (bundleLabels.length <= iframeLabels.length) {
      console.log(
        `[Lockstep] remapping ${bundleLabels.length} labels by position: ` +
        `[${bundleLabels.slice(0, 3).join(",")}] → [${iframeLabels.slice(0, 3).join(",")}]`
      );
      for (let i = 0; i < frame.steps.length && i < iframeLabels.length; i++) {
        frame.steps[i].label = iframeLabels[i];
      }
      return true;
    }

    // More bundle steps than iframe labels — can't remap reliably
    console.log(
      `[Lockstep] label count mismatch: ` +
      `bundle=${bundleLabels.length} iframe=${iframeLabels.length}`
    );
    return false;
  }

  private queryLabelsFromIframe(): Promise<string[]> {
    return new Promise((resolve) => {
      let done = false;
      const finish = (labels: string[]) => {
        if (done) return;
        done = true;
        window.removeEventListener("message", handler);
        clearTimeout(timer);
        resolve(labels);
      };
      const handler = (e: MessageEvent) => {
        if (e.data?.event === "labelsResponse" && Array.isArray(e.data.labels)) {
          finish(e.data.labels);
        }
      };
      window.addEventListener("message", handler);
      this.sendToIframe({ action: "queryLabels" });
      const timer = setTimeout(() => finish([]), QUERY_LABELS_TIMEOUT_MS);
    });
  }

  /**
   * Fallback for old iframe templates: seek to a label, wait for stepChanged.
   * Sends seekToStep twice — first to a dummy position to reset the dedup
   * tracker, then to the actual label.
   */
  private verifyLabelBySeek(firstLabel: string): Promise<boolean> {
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
          finish(true);
        }
      };
      window.addEventListener("message", handler);
      this.sendToIframe({ action: "seekToStep", label: firstLabel });

      const timer = setTimeout(() => {
        finish(false);
      }, QUERY_LABELS_TIMEOUT_MS);
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
