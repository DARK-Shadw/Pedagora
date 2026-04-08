"""TEST 6: Prefetch architecture validation.

The hypothesis: while frame N plays (~30-50s), we can generate frame N+1's
audio in a background thread. By the time the user reaches frame N+1, its
audio is already cached.

We test this by:
1. Generating frame 0 audio synchronously (this is the only blocking wait)
2. Immediately spawning background gen for frames 1-18
3. Simulating playback of frame 0 (~50s)
4. Checking how many later frames are already done

Goal: by the time frame 0 finishes, ALL remaining frames should be ready.
"""

import os
import sys
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from piper import PiperVoice, SynthesisConfig

VOICE_DIR = os.path.join(os.path.dirname(__file__), "piper_voices")
VOICE_PATH = os.path.join(VOICE_DIR, "en_US-libritts_r-medium.onnx")

# Realistic frame speeches — varying lengths matching what an LLM would produce
FRAME_SPEECHES = {
    "f01": [
        "Look at this animation. Right now you are seeing pure random noise filling the screen.",
        "Now watch carefully. Patterns are starting to emerge from the chaos, regions of light and dark.",
        "See where the camera is zooming in. A face is coming into focus from what was just noise.",
        "What do you think this process represents? Take a moment to think about it before we continue.",
    ],
    "f02": [
        "Look at this split screen, what catches your eye, the smooth Gaussian on the left.",
        "Notice how the glowing arrow labeled YOUR MODEL is bridging these two distributions together.",
        "See where the particles are flowing, from a simple spherical Gaussian into a complex landscape.",
        "Now, take a step back and think about how this process might apply to other domains.",
        "This is the core insight behind diffusion models — learning to invert noise into structure.",
    ],
    "f03": [
        "Look at this animation, see where the glowing dots are falling from above.",
        "Now, notice how the histogram's outline is changing, becoming smoother with each new sample.",
        "Watch closely as the bars grow and shrink, converging toward a stable shape.",
        "See the underlying curve revealing itself — this is the Gaussian we are sampling from.",
        "After enough samples, the histogram closely matches the true distribution.",
        "This is what we mean when we say a distribution is the limit of empirical samples.",
    ],
    "f04": [
        "Look at this Gaussian distribution.",
        "The empirical rule states that sixty eight percent of data lies within one sigma.",
        "Let me show you what changing the mean does.",
        "And here is what changing sigma does.",
        "These two parameters fully describe a Gaussian.",
    ],
    "f05": [
        "Here is a different view.",
        "Notice the axes.",
        "Watch this transition.",
        "And here is the result.",
        "Quite striking, isn't it.",
        "Let me explain what just happened.",
    ],
    "f06": [
        "Look at this dart throw analogy.",
        "Each dart represents a noise sample being decoded.",
        "Now watch the decoder transform noise into a target image.",
    ],
    "f07": ["A short single-step demonstration.", "Watch this transition.", "Notice the change.", "And we're done."],
    "f08": ["Step one of this concept.", "Step two reveals more.", "Step three shows the relationship.", "Final step."],
    "f09": ["Introduction to the concept.", "Setting up the graphical model.", "Applying Bayes theorem.", "Why direct computation is intractable."],
    "f10": [
        "Here is a question for you to think about.",
        "I'm going to wait while you consider it.",
        "Now let me reveal the answer.",
        "And here is why it works.",
    ],
    "f11": [
        "Introduction to KL divergence.",
        "Two distributions side by side.",
        "Computing the log ratio.",
        "Weighted by the first distribution.",
        "Notice the asymmetry of KL.",
    ],
    "f12": [
        "Setting up the training scenario.",
        "Initializing the variational distribution.",
        "Running the optimization loop, watching it converge.",
        "After convergence, the distributions match.",
    ],
    "f13": [
        "Introduction to expectation.",
        "Computing the weighted average.",
        "Visualizing as a balance beam.",
        "Now the second moment, expectation of x squared.",
        "Putting it all together.",
    ],
    "f14": ["This is the simple intro frame for variational inference."],
    "f15": [
        "Introduction to Monte Carlo methods.",
        "Sampling from the distribution.",
        "Computing the KL divergence estimate.",
        "Terminal value after many samples.",
    ],
    "f16": [
        "Welcome to the VAE walkthrough.",
        "Step one, the prior distribution.",
        "Step two, the encoder network.",
        "Step three, the decoder network.",
        "Step four, computing the KL term.",
        "Step five, computing the ELBO.",
        "Step six, the full loss equation.",
        "Step seven, the training loop.",
        "And the finale, putting it all together.",
    ],
    "f17": [
        "Introducing the challenge.",
        "Stating the problem clearly.",
        "Here is solution A.",
        "And here is solution B, which is generally better.",
    ],
    "f18": [
        "Starting from pure noise.",
        "Watching emergence happen slowly.",
        "A face begins to form clearly.",
        "Then a video sequence unfolds.",
        "And the final synthesis is complete.",
    ],
    "f19": [
        "Concluding the lesson.",
        "Summarizing the key takeaways.",
        "Final words and encouragement.",
    ],
}


def synth_frame(voice, cfg, speeches: list[str]) -> tuple[float, float]:
    """Synthesize all step audios for one frame. Returns (synth_time, audio_duration)."""
    t0 = time.time()
    total_audio_bytes = 0
    sr = 22050
    for text in speeches:
        for chunk in voice.synthesize(text, syn_config=cfg):
            total_audio_bytes += len(chunk.audio_int16_bytes)
            sr = chunk.sample_rate
    elapsed = time.time() - t0
    audio_dur = total_audio_bytes / 2 / sr
    return elapsed, audio_dur


def main():
    print("=" * 70)
    print("TEST 6: Prefetch architecture validation")
    print("=" * 70)

    print("\n1. Loading Piper (LibriTTS-R medium)...")
    voice = PiperVoice.load(VOICE_PATH)
    cfg = SynthesisConfig()
    print("   Loaded")

    # Warm up
    list(voice.synthesize("warmup", syn_config=cfg))

    frames = list(FRAME_SPEECHES.items())
    total_frames = len(frames)
    print(f"\n2. Will simulate {total_frames} frames")

    # Cache for completed frame audio
    cache_lock = threading.Lock()
    audio_cache: dict[str, dict] = {}
    synth_log = []

    def background_synth(frame_id, speeches, voice, cfg):
        """Generate audio for one frame and put in cache."""
        elapsed, audio_dur = synth_frame(voice, cfg, speeches)
        with cache_lock:
            audio_cache[frame_id] = {"synth_s": elapsed, "audio_s": audio_dur, "ready_at": time.time()}
            synth_log.append((frame_id, elapsed, audio_dur, time.time()))

    # 3. SCENARIO A: Generate frame 0 sync, then start prefetch in background
    print("\n3. SCENARIO A: Generate frame 0, start prefetch, simulate playback")
    print("-" * 70)

    pipeline_start = time.time()

    # Generate frame 0 (blocking — user waits this long for "splash screen")
    f0_id, f0_speeches = frames[0]
    f0_synth_t, f0_audio_t = synth_frame(voice, cfg, f0_speeches)
    audio_cache[f0_id] = {"synth_s": f0_synth_t, "audio_s": f0_audio_t, "ready_at": time.time()}
    print(f"   [{f0_synth_t:5.2f}s] Frame 0 ready ({f0_audio_t:.0f}s audio) - STUDENT CAN START")

    splash_wait = time.time() - pipeline_start
    print(f"\n   ===> User splash screen: {splash_wait:.1f}s")

    # Start background prefetch for remaining frames
    # We use a single thread to NOT contend with main playback
    # (in real Pipe app, this is in a separate process / different worker)
    prefetch_executor = ThreadPoolExecutor(max_workers=1)
    for fid, speeches in frames[1:]:
        prefetch_executor.submit(background_synth, fid, speeches, voice, cfg)

    # Simulate frame 0 playback
    print(f"\n   Simulating frame 0 playback ({f0_audio_t:.0f}s + animation pauses)...")
    # Lockstep playback time = sum of audio + sum of inter-step gaps
    # We have step gaps from animation_timings.json — for f01: 5+10+12+23 = 50s total
    f01_total = 50.0  # from animation timing
    # Real playback wait
    playback_target = f01_total
    playback_start = time.time()

    # Print cache state every 5 seconds
    last_check = 0
    while time.time() - playback_start < playback_target:
        elapsed = time.time() - playback_start
        if elapsed - last_check >= 5:
            with cache_lock:
                ready = list(audio_cache.keys())
            print(f"   [{elapsed:5.1f}s playback] Cached frames: {len(ready)}/{total_frames} -> {ready}")
            last_check = elapsed
        time.sleep(0.5)

    print(f"\n   Frame 0 playback finished after {playback_target:.0f}s")
    with cache_lock:
        ready_at_end = list(audio_cache.keys())
    print(f"   Cache state: {len(ready_at_end)}/{total_frames} frames ready")

    # Wait for prefetch to fully complete
    prefetch_executor.shutdown(wait=True)
    total_wall = time.time() - pipeline_start

    print(f"\n4. Final results:")
    print(f"   Splash wait: {splash_wait:.1f}s")
    print(f"   Total prefetch wall time: {total_wall:.1f}s")
    print(f"   Frames pre-cached during frame 0 playback: {len(ready_at_end) - 1}/{total_frames - 1}")

    # Check: was every frame ready BEFORE its turn?
    print(f"\n5. Per-frame ready time vs simulated playback time:")
    print(f"   {'Frame':<8} {'Synth (s)':<12} {'Audio (s)':<12} {'Ready at (s from start)':<25}")
    cumulative_play_time = 0
    miss_count = 0
    for i, (fid, speeches) in enumerate(frames):
        with cache_lock:
            entry = audio_cache.get(fid)
        if not entry:
            print(f"   {fid:<8} NOT GENERATED")
            continue
        ready_at = entry["ready_at"] - pipeline_start
        synth_s = entry["synth_s"]
        audio_s = entry["audio_s"]
        ready_in_time = "PRE-CACHED" if ready_at <= cumulative_play_time + splash_wait else f"LATE (+{ready_at - cumulative_play_time - splash_wait:.1f}s)"
        if "LATE" in ready_in_time:
            miss_count += 1
        print(f"   {fid:<8} {synth_s:<12.2f} {audio_s:<12.1f} {ready_at:<6.1f}s ({ready_in_time})")
        cumulative_play_time += audio_s + 5  # rough estimate of animation gaps

    print(f"\n   Cache misses (frames not ready when needed): {miss_count}/{total_frames}")
    if miss_count == 0:
        print("   ===> SUCCESS: every frame was ready before playback reached it")
    else:
        print(f"   ===> {miss_count} cache misses — need a different prefetch strategy")


if __name__ == "__main__":
    main()
