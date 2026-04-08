# Animation-TTS Sync Investigation — Findings & Recommendation

**Date**: 2026-04-07
**Investigation goal**: Diagnose and propose a perfect-sync solution for the 4 issues you reported.

---

## Issues You Reported

| # | Issue | Root Cause Found |
|---|---|---|
| 1 | ~1min of nothing at lesson start | Kokoro TTS opening synthesis: 24s + LLM call + WS overhead |
| 2 | Empty "Animation will appear here" during greeting | Frontend doesn't show first frame until after opening speech |
| 3 | Speech plays AFTER animation has moved past it | Animation starts playing BEFORE speech is generated/synthesized |
| 4 | Failed animations show blank screen | HTML elements created with `opacity:0`, GSAP fades them in. If GSAP errors, opacity stays 0 → blank |

All four are confirmed reproducible.

---

## Tests Run

| Test | What it measured | Result |
|---|---|---|
| **test1_kokoro_baseline.py** | Kokoro speed | Cold start 1.68s, long opening 23.86s, 1.16x realtime max |
| **test2_animation_timing.py** | All 19 frames' GSAP labels + durations | Step gaps range from 0.9s to 126s. Also found f14 + f19 broken |
| **test3_sync_prototype.py** | Lockstep sync with Kokoro on f01 | Perfect zero-drift sync, but 30.5s pre-gen wait |
| **test4_piper.py** | Piper TTS speed | **13x faster than Kokoro**, 241ms first chunk, 1.96s for full opening |
| **test5_piper_quality.py** | Sync prototype with Piper on f01 | Perfect sync, 6.6s pre-gen (5x faster than Kokoro) |
| **test6_prefetch.py** | Background prefetch all 19 frames | **2.0s splash, 12.8s all frames cached, ZERO cache misses** |
| **test7_quality_compare.py** | Side-by-side voice samples | Saved Kokoro + 4 Piper voices for A/B test |
| **test8_edge_cases.py** | Math text + broken animation visual | Math handled OK, broken animations DO show blank screen |

---

## Key Numerical Findings

### Kokoro TTS (current)
| Metric | Value |
|---|---|
| Cold start | 1.68s |
| Realtime factor (long text) | 1.16x |
| Long opening synth (478 chars) | 23.86s |
| First-sentence floor | 2.2s (parallel) |
| Sync prototype pre-gen for f01 (4 chunks) | **30.5s** |

### Piper TTS (proposed)
| Metric | Value | vs Kokoro |
|---|---|---|
| Cold start | 3.16s | 1.9x slower |
| Realtime factor (long text) | **13.21x** | **11x faster** |
| Long opening synth (478 chars) | **1.96s** | **12x faster** |
| First chunk (streaming) | **241ms** | **29x faster** |
| Sync prototype pre-gen for f01 (4 chunks) | **6.6s** | **5x faster** |
| All 19 frames pre-gen | **12.8s** | N/A — prefetch makes this background |
| Model size | 60-108MB | smaller (Kokoro 338MB) |

### Prefetch architecture validation
- **Splash wait**: 2.0s (only frame 0 generated synchronously)
- **Background prefetch of remaining 18 frames**: completes in 12.8s
- **Frame 0 playback duration**: 50s — masks all the prefetch
- **Cache misses**: **0** (every frame ready before user reaches it)

---

## Why Kokoro Streaming Isn't Enough

I tested whether Kokoro's parallelism could save it:
- 5 short sentences (~50ch each): parallel speedup 4.8x ✓
- 4 medium sentences (~120ch each): parallel speedup essentially **0x** ✗

Kokoro is CPU-bound. Threads contend for the same cores. Parallelism only helps for very small payloads. For realistic teaching speech (100+ chars per chunk), threads gain almost nothing. This is a fundamental architectural issue with kokoro_onnx + Python threading on CPU.

**Switching engines is the only way to get meaningful speedup on CPU.**

---

## Why Piper Wins

1. **True streaming API**: `voice.synthesize()` returns `Iterable[AudioChunk]` — yields chunks as they're generated, no need to wait for full text
2. **espeak-ng phonemizer** under the hood — battle-tested for natural speech
3. **VITS architecture** with smaller, faster models than Kokoro
4. **Multiple voices**: Lessac (US female, current candidate), LibriTTS-R (multi-speaker, often best quality), Amy (popular friendly), and 70+ others
5. **Same drop-in pattern**: load ONNX, call synthesize, get audio. No backend changes beyond swapping the call.
6. **Free, open source, local** — no API keys, no rate limits, no privacy concerns

**Voice quality**: 5 samples saved at `sync_tests/voice_comparison/`. Listen to:
- `1_kokoro_af_bella.wav` (current)
- `2_piper_lessac_medium.wav`
- `3_piper_lessac_high.wav`
- `4_piper_libritts_medium.wav` (my recommendation — natural prosody)
- `5_piper_amy_medium.wav`

---

## Proposed Architecture (Issue-by-Issue)

### Issue 1 + 2: 1-min wait + empty screen

**Fix**:
1. **Switch TTS to Piper** (one file change in `services/tts.py`)
2. **Pre-generate at session create**: when WebSocket connects, immediately start generating frame 0 audio
3. **Show frame 0 + lesson title overlay BEFORE speech is ready** — visual is up in <1s
4. **Splash state**: lesson title + "AI teacher preparing..." indicator for ~2 seconds while Piper generates frame 0
5. **Background prefetch**: remaining 18 frames generated during frame 0 playback (12.8s, fits comfortably in 50s playback)

**Result**: User clicks Start → 0.5s for animation iframe to render frame 0 → ~2s for first audio → lesson plays.

### Issue 3: Speech plays after animation has moved past it

**Root cause** (confirmed by test 3):
- Current `_teach_without_steps` flow yields `animation_control:play` BEFORE generating speech
- Animation runs freely while speech is generated
- By the time chunk N is sent, animation has moved past where chunk N's content is

**Fix**: **Lockstep sync** (proven perfect in test 3 + test 5):
- Pre-generate ALL chunks for the frame (already done by prefetch)
- Animation has GSAP step labels (already exists in all 19 animations except f14/f19)
- Frontend protocol per step:
  1. `tl.seek(stepN_time); tl.pause()` (animation frozen at step N visual)
  2. Play audio chunk N
  3. On audio.onended → `tl.tweenFromTo(stepN_time, stepN+1_time)` (animation runs naturally to next step)
  4. On tween onComplete → repeat for step N+1
- Perfect sync: speech "look at the pixels" plays WHILE pixels are visible, then animation morphs

**Validation**: test3 + test5 both confirmed zero-drift sync. The user sees:
- 5.3s of speech with paused animation (intro state)
- 5.0s of animation morphing intro → emergence
- 5.4s of speech with paused animation (emergence state)
- 10.0s of animation morphing emergence → zoom
- 5.1s of speech with paused animation (zoom state)
- ... etc

### Issue 4: Failed animations show blank screen

**Confirmed**: tested with f14 (`shimSVG.node is not a function` error). Screenshot shows pure dark background — no visual content. The HTML elements exist (children=3) but they have `opacity:0` and GSAP errored before fading them in.

**Fix**: Add a **frame loader fallback overlay** to the iframe wrapper:
- Always-visible title overlay (top-left): "Lesson title — Frame N: title"
- Iframe with animation
- onError handler on iframe + JS error detector
- If iframe reports an error OR doesn't fire `stepChanged` within 3s of being shown:
  - Show fallback panel with frame title + description + a generic icon
  - Audio still plays normally
- Demo screenshot at `sync_tests/edge_cases/fallback_demo.png` shows what this looks like

**Bonus**: also fix f14 + f19 the same way f02 was fixed (one regex pattern across all animation files).

---

## Final Architecture

```
SESSION CREATE (one-time, ~2s)
├─ Create teaching session row
├─ Pre-load Piper model (~3s, hidden during onboarding navigation)
├─ Generate frame 0 audio (synchronous, ~1.5-2s)
└─ Mark session "ready"

SPLASH SCREEN (frontend, ~1-2s)
├─ Show lesson title
├─ Show "AI teacher preparing your lesson..."
└─ As soon as session=ready: dismiss splash

FRAME 0 PLAYBACK
├─ Frontend immediately renders iframe with f01.html (animation paused at intro state)
├─ Title overlay always visible
├─ Background: prefetcher generates frames 1-18 audio (~13s total wall time)
├─ Lockstep sync engine in frontend:
│   for each step in frame:
│     - tl.seek(step.anim_time); tl.pause()
│     - play audio chunk N
│     - on ended: tl.tweenFromTo(stepN, stepN+1)
│     - on tween complete: next iteration
└─ Cumulative: lesson plays for ~50s, all subsequent frames cached by then

NEXT FRAMES (1..18)
├─ Audio already cached → instant transition
├─ Iframe loads next frame's HTML
├─ Title overlay updates
└─ Lockstep sync repeats
```

---

## Self-Critique: Will This Actually Work?

### "Will Piper voice quality be good enough?"
- Listen to the 5 samples in `sync_tests/voice_comparison/`. If LibriTTS-R or Lessac-high sounds acceptable to you, we're good.
- Worst case: you don't like any of them, we keep Kokoro and accept ~10s splash + use sentence streaming for opening only. Not perfect but better than current.

### "What if pre-gen takes longer for some lessons?"
- Tested with realistic LLM-style speeches across 19 frames (all of them). Worst-case frame: 2.2s synth time. This is the f01 case we have.
- For exotic lessons with very long speeches, prefetch might take 30s instead of 13s. Still fits in playback time.
- Fallback: if prefetch is slower than playback, the lesson naturally pauses at frame N+1 with a brief loader until audio arrives.

### "What if the animation has only 1 step (like f14)?"
- 1-step animations: no inter-step lockstep needed. Just play the whole speech, animation runs in background.
- This is the current `_teach_without_steps` path which already works.

### "What about animations with very short step gaps (0.9s in f05)?"
- Speech for that step might be longer than 0.9s of animation
- Solution: animation pauses at next step until speech finishes (we already do this by design)
- Visual experience: brief "freeze frame" between steps — totally acceptable

### "What about animations with 126s gaps (f12 training loop)?"
- One speech chunk for 126s of animation = unworkable (chunk would be 30+ sentences)
- Solution: at content-generation time, the LLM should produce SUB-CHUNKS for long segments. The animation can have implicit "phase markers" within a long segment.
- For now: just generate one ~15s chunk, then animation plays silently for the rest. Not perfect but acceptable.

### "What if user pauses/resumes mid-speech?"
- Current `speech_done` protocol still works
- Audio.pause()/resume() in frontend
- Animation paused via tl.pause()
- Resume: continue from same position

### "Will the frontend lockstep code be complex?"
- Test 3 + 5 prototype was ~50 lines of JS — very simple
- The protocol is just: seek → play audio → await onended → tweenFromTo → await onComplete → loop
- No state machine, no edge cases beyond pause/resume

### "What's the migration risk?"
- Backend: replace `services/tts.py` (10 lines of actual logic change) and add prefetch in session manager
- Frontend: rewrite the AudioContext playback to use the lockstep engine
- Database: no schema changes
- Animation files: no changes (the existing 19 already have step labels)
- Rollback: keep Kokoro available as a feature flag, A/B test with real users

---

## Recommendations (in order of priority)

### Critical (do this work)
1. **Switch TTS engine to Piper** — `services/tts.py` rewrite (~30 lines)
2. **Pre-generate frame 0 at session create** — small change in `session_manager.py`
3. **Show first frame BEFORE opening speech** — `FrameNavigator.run()` reorder
4. **Background prefetch for remaining frames** — new module `audio_cache.py`
5. **Frontend lockstep sync engine** — new file in `(classroom)/v2/lib/sync.ts`
6. **Title overlay + fallback panel** — new component
7. **Animation step extraction** — already in plan from before, ~10 lines in `teacher.py`

### Important (do soon after)
8. Fix f14 + f19 the same way f02 was fixed (small regex script over generated_visuals/)
9. Add `prefetch_progress` field to session so UI can show "Preparing lesson 12/19..."

### Nice to have (later)
10. Animation generation: enforce shorter step gaps in prompts (max 30s between labels)
11. LLM speech generation: tighten prompts to produce shorter chunks (2-3 sentences max)

---

## Files Created During Investigation

All in `sync_tests/` (separate from production code):
- `test1_kokoro_baseline.py` — TTS speed measurements
- `test2_animation_timing.py` — extract GSAP labels from all 19 frames
- `test3_sync_prototype.py` — lockstep prototype with Kokoro
- `test4_piper.py` — Piper benchmark
- `test5_piper_quality.py` — Piper sync prototype + voice comparison
- `test6_prefetch.py` — background prefetch validation
- `test7_quality_compare.py` — side-by-side voice samples
- `test8_edge_cases.py` — math text, broken animation, fallback overlay
- `animation_timings.json` — extracted timing data for all frames
- `voice_comparison/*.wav` — 5 voice samples for A/B listening
- `edge_cases/*.png` — broken animation + fallback demo screenshots
- `piper_voices/` — downloaded Piper voice models (60-108MB each)

**Nothing in the production codebase has been modified.**

---

## What I Need From You

1. **Listen to the 5 voice samples** in `sync_tests/voice_comparison/` and tell me which one you prefer (or if Kokoro Bella is so much better you'd rather keep it and accept a longer splash)
2. **Approve the architecture** above so I can write a precise implementation plan
3. Decide whether to fix f14 + f19 in this same effort or as a separate cleanup

Once you've picked the voice, I'll write the implementation plan in detail and we proceed.
