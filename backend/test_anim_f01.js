// ── Frame f01: Randomness → Face  (50s, 4 labeled steps) ─────────────────────
var container = document.getElementById('canvas-container');
var W = container.clientWidth  || window.innerWidth;
var H = container.clientHeight || window.innerHeight;
container.style.background = '#0d1117';
container.style.overflow   = 'hidden';
container.style.position   = 'relative';

// ── Zoom wrapper (transform-origin tuned to eye region) ───────────────────────
var zoomWrap = document.createElement('div');
Object.assign(zoomWrap.style, {
  position: 'absolute', top: '0', left: '0', width: '100%', height: '100%',
  transformOrigin: '52% 36%', overflow: 'hidden'
});
container.appendChild(zoomWrap);

// ── LAYER 1: Face image ────────────────────────────────────────────────────────
var faceImg = document.createElement('img');
faceImg.src =
  'https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?w=800&q=80&fit=crop&crop=face';
Object.assign(faceImg.style, {
  position: 'absolute', top: '50%', left: '50%',
  transform: 'translate(-50%,-50%)',
  minWidth: '100%', minHeight: '100%', objectFit: 'cover',
  opacity: '0', zIndex: '1'
});
zoomWrap.appendChild(faceImg);

// ── LAYER 2: Noise canvas ─────────────────────────────────────────────────────
var noiseCanvas = document.createElement('canvas');
noiseCanvas.width = W; noiseCanvas.height = H;
Object.assign(noiseCanvas.style, {
  position: 'absolute', top: '0', left: '0', width: '100%', height: '100%', zIndex: '2'
});
zoomWrap.appendChild(noiseCanvas);
var ctx = noiseCanvas.getContext('2d');

// Small off-screen canvas — stretch to create blocky pixelated noise
var NW = 160, NH = 120;
var smallCvs = document.createElement('canvas');
smallCvs.width = NW; smallCvs.height = NH;
var sCtx = smallCvs.getContext('2d');

// ── LAYER 3: Vignette ─────────────────────────────────────────────────────────
var vignette = document.createElement('div');
Object.assign(vignette.style, {
  position: 'absolute', top: '0', left: '0', width: '100%', height: '100%',
  zIndex: '3', pointerEvents: 'none',
  background: 'radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.65) 100%)'
});
zoomWrap.appendChild(vignette);

// ── LAYER 4: Floating pixel numbers ───────────────────────────────────────────
var numOverlay = document.createElement('div');
Object.assign(numOverlay.style, {
  position: 'absolute', top: '0', left: '0', width: '100%', height: '100%',
  overflow: 'hidden', opacity: '0', pointerEvents: 'none', zIndex: '4'
});
(function buildNumbers() {
  var frag   = document.createDocumentFragment();
  var colors = ['#3B82F6', '#8B5CF6', '#22C55E', '#EF4444', '#F59E0B'];
  for (var i = 0; i < 380; i++) {
    var sp  = document.createElement('span');
    // Box-Muller — Gaussian samples look more authentic than uniform
    var u1  = Math.random() || 1e-9, u2 = Math.random();
    var val = Math.round(Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2) * 45 + 128);
    sp.textContent = Math.max(0, Math.min(255, val));
    Object.assign(sp.style, {
      position: 'absolute',
      left: (Math.random() * 93 + 3.5) + '%',
      top:  (Math.random() * 93 + 3.5) + '%',
      color: colors[i % colors.length],
      fontSize: (9 + Math.random() * 7) + 'px',
      fontFamily: "'JetBrains Mono','Fira Code',monospace",
      opacity: (0.35 + Math.random() * 0.65).toFixed(2),
      textShadow: '0 0 6px currentColor'
    });
    frag.appendChild(sp);
  }
  numOverlay.appendChild(frag);
})();
zoomWrap.appendChild(numOverlay);

// ── LAYER 5: Distribution equation ───────────────────────────────────────────
var eqBox = document.createElement('div');
Object.assign(eqBox.style, {
  position: 'absolute', bottom: '8%', left: '50%', transform: 'translateX(-50%)',
  opacity: '0', zIndex: '5', pointerEvents: 'none',
  background: 'rgba(13,17,23,0.85)', padding: '14px 32px', borderRadius: '12px',
  border: '1px solid rgba(59,130,246,0.4)',
  boxShadow: '0 0 40px rgba(59,130,246,0.2)', whiteSpace: 'nowrap'
});
katex.render(
  'X_{\\text{pixel}} \\sim \\mathcal{N}(\\mu,\\,\\sigma^2)',
  eqBox, { throwOnError: false, displayMode: true }
);
zoomWrap.appendChild(eqBox);

// ── LAYER 6: Subtitle bar ─────────────────────────────────────────────────────
var subtitle = document.createElement('div');
Object.assign(subtitle.style, {
  position: 'absolute', top: '18px', left: '50%', transform: 'translateX(-50%)',
  color: '#8b949e', fontSize: '13px',
  fontFamily: "-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
  opacity: '0', zIndex: '15', letterSpacing: '2.5px', textTransform: 'uppercase',
  background: 'rgba(13,17,23,0.75)', padding: '7px 20px', borderRadius: '6px',
  border: '1px solid #30363d', whiteSpace: 'nowrap'
});
container.appendChild(subtitle);

// ── LAYER 7: Question overlay (outside zoom so it stays centered) ─────────────
var qDiv = document.createElement('div');
Object.assign(qDiv.style, {
  position: 'absolute', top: '0', left: '0', width: '100%', height: '100%',
  display: 'flex', flexDirection: 'column', alignItems: 'center',
  justifyContent: 'center', opacity: '0', zIndex: '20', pointerEvents: 'none'
});

var qMark = document.createElement('div');
qMark.id = 'q-mark';
qMark.textContent = '?';
Object.assign(qMark.style, {
  fontSize: 'clamp(80px,14vw,150px)', color: '#F59E0B', fontWeight: '700',
  fontFamily: 'Georgia,serif', marginBottom: '28px', lineHeight: '1',
  textShadow: '0 0 40px rgba(245,158,11,0.6), 0 0 90px rgba(245,158,11,0.3)'
});
qDiv.appendChild(qMark);

var qText = document.createElement('div');
qText.innerHTML =
  'How does randomness become ' +
  '<span style="color:#3B82F6;text-shadow:0 0 16px rgba(59,130,246,0.7)">THIS</span>?';
Object.assign(qText.style, {
  fontSize: 'clamp(18px,3.2vw,40px)', color: '#c9d1d9',
  fontFamily: "-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
  fontWeight: '600', letterSpacing: '0.4px',
  textAlign: 'center', padding: '0 24px'
});
qDiv.appendChild(qText);
container.appendChild(qDiv);

// ── Shared animated state (modified by GSAP tweens) ──────────────────────────
var S = {
  noiseAlpha: 1,    // noise layer opacity
  noiseRes:   0.08, // noise block size (fraction of NW×NH; small = chunky pixels)
  faceAlpha:  0,    // face image opacity
  faceDim:    1,    // extra dimming for question step
  zoom:       1,
  numAlpha:   0,
  eqAlpha:    0,
  qAlpha:     0,
  qGlow:      0,
  subAlpha:   0
};

// ── Render loop (runs every RAF) ──────────────────────────────────────────────
function render() {
  // Draw pixelated noise
  var res = Math.max(0.04, S.noiseRes);
  var nw  = Math.max(4, Math.round(NW * res));
  var nh  = Math.max(3, Math.round(NH * res));
  var id  = sCtx.createImageData(nw, nh);
  var d   = id.data;
  for (var i = 0; i < d.length; i += 4) {
    d[i]   = Math.random() * 255;
    d[i+1] = Math.random() * 255;
    d[i+2] = Math.random() * 255;
    d[i+3] = 255;
  }
  sCtx.putImageData(id, 0, 0);
  ctx.imageSmoothingEnabled = false;
  ctx.clearRect(0, 0, W, H);
  ctx.drawImage(smallCvs, 0, 0, nw, nh, 0, 0, W, H);
  ctx.imageSmoothingEnabled = true;

  // Apply state to DOM
  noiseCanvas.style.opacity   = S.noiseAlpha;
  faceImg.style.opacity       = S.faceAlpha * S.faceDim;
  zoomWrap.style.transform    = 'scale(' + S.zoom + ')';
  numOverlay.style.opacity    = S.numAlpha;
  eqBox.style.opacity         = S.eqAlpha;
  qDiv.style.opacity          = S.qAlpha;
  subtitle.style.opacity      = S.subAlpha;

  // Pulse glow on question mark
  var g = 40 + S.qGlow * 90;
  qMark.style.textShadow =
    '0 0 ' + g        + 'px rgba(245,158,11,0.75),' +
    '0 0 ' + (g * 2)  + 'px rgba(245,158,11,0.35)';
}
gsap.ticker.add(render);

// ─────────────────────────────────────────────────────────────────────────────
// TIMELINE  (50 s total, 4 labeled steps)
// ─────────────────────────────────────────────────────────────────────────────

// ── STEP 1: Pure static noise (0 → 8s) ───────────────────────────────────────
tl.addLabel('static-noise', 0);

tl.set(S, { noiseAlpha: 1, faceAlpha: 0, noiseRes: 0.08 }, 0);

tl.call(function () { subtitle.textContent = 'Pure Random Noise'; }, [], 0.4);
tl.to(S, { subAlpha: 0.85, duration: 1, ease: 'power2.out' }, 0.4);

// Noise block size drifts — signals early "organization" even while still chaotic
tl.to(S, { noiseRes: 0.18, duration: 3, ease: 'steps(6)' }, 0);
tl.to(S, { noiseRes: 0.32, duration: 3, ease: 'steps(5)' }, 3);
tl.to(S, { noiseRes: 0.45, duration: 2, ease: 'power1.in' }, 6);

// ── STEP 2: Face emergence — noise fades, face sharpens (8 → 25s) ────────────
tl.addLabel('face-emergence', 8);

tl.call(function () { subtitle.textContent = 'Patterns Emerging…'; }, [], 8.2);

// Phase A — ghost of face through heavy noise
tl.to(S, { faceAlpha: 0.25, noiseAlpha: 0.88, noiseRes: 0.20, duration: 4, ease: 'power1.inOut' }, 8);

// Phase B — face gaining contrast
tl.to(S, { faceAlpha: 0.55, noiseAlpha: 0.55, noiseRes: 0.50, duration: 4, ease: 'power2.inOut' }, 12);

tl.call(function () { subtitle.textContent = 'Structure From Chaos'; }, [], 14.5);

// Phase C — clearly a face, thin grain overlay
tl.to(S, { faceAlpha: 0.88, noiseAlpha: 0.22, noiseRes: 0.82, duration: 4, ease: 'power2.inOut' }, 16);

// Phase D — pristine photo, noise gone
tl.to(S, { faceAlpha: 1.0, noiseAlpha: 0.0, noiseRes: 1.0, duration: 3, ease: 'power2.out' }, 20);

tl.to(S, { subAlpha: 0, duration: 1.5, ease: 'power2.in' }, 22.5);

// ── STEP 3: Zoom into eye — pixel grid + distribution (25 → 40s) ─────────────
tl.addLabel('zoom-pixels', 25);

// Slow cinematic zoom toward eye
tl.to(S, { zoom: 6.5, duration: 8, ease: 'power2.inOut' }, 25);

// Fine grain noise re-appears over zoomed face (shows individual pixels)
tl.to(S, { noiseAlpha: 0.30, noiseRes: 1.0, duration: 3, ease: 'power1.inOut' }, 29);

// Floating pixel values fade in
tl.to(S, { numAlpha: 0.88, duration: 3, ease: 'power2.inOut' }, 30);

// Distribution equation
tl.to(S, { eqAlpha: 1, duration: 2, ease: 'power2.inOut' }, 33);

tl.call(function () { subtitle.textContent = 'Just Numbers From Distributions'; }, [], 31);
tl.to(S, { subAlpha: 0.85, duration: 1.5, ease: 'power2.out' }, 31);

// Shimmer every 3rd number (living data feel)
gsap.to(numOverlay.querySelectorAll('span:nth-child(3n)'), {
  opacity: 0.15, duration: 0.9, yoyo: true, repeat: -1, ease: 'sine.inOut', stagger: 0.06
});

// Hold on zoomed frame
tl.to({}, { duration: 5 }, 35);

// ── STEP 4: Question reveal (40 → 50s) ───────────────────────────────────────
tl.addLabel('question-reveal', 40);

// Zoom back out
tl.to(S, { zoom: 1.0, duration: 3.5, ease: 'power2.inOut' }, 40);

// Clear all data overlays
tl.to(S, { numAlpha: 0, eqAlpha: 0, noiseAlpha: 0, subAlpha: 0, duration: 2.5, ease: 'power2.inOut' }, 40);

// Dim face so question text pops
tl.to(S, { faceDim: 0.38, duration: 2.5, ease: 'power2.inOut' }, 41.5);

// Question mark fades in
tl.to(S, { qAlpha: 1, duration: 2, ease: 'power2.out' }, 43.5);

// Pulsing glow — 3 full beats
tl.to(S, { qGlow: 1, duration: 1.0, ease: 'sine.inOut', yoyo: true, repeat: 5 }, 44.5);

// Hold final frame
tl.to({}, { duration: 1.5 }, 48.5);

// ── Public API ────────────────────────────────────────────────────────────────
window.animationAPI = {
  timeline: tl,
  getSteps: function () { return Object.keys(tl.labels); },
  seekToStep: function (label) { tl.seek(label); tl.pause(); },
  play:  function () { tl.play(); },
  pause: function () { tl.pause(); },
  getCurrentStep: function () {
    var t = tl.time(), cur = '';
    for (var name in tl.labels) { if (tl.labels[name] <= t) cur = name; }
    return cur;
  }
};
