"""HTML templates for visual frames.

FRAME_HTML_TEMPLATE — browser-rendered (GSAP + D3 + KaTeX)
VIDEO_HTML_TEMPLATE — Manim-rendered MP4 wrapped in same animationAPI interface
"""

FRAME_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-tomorrow.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-python.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #0d1117; color: #c9d1d9;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    width: 100vw; height: 100vh; overflow: hidden;
    display: flex; align-items: center; justify-content: center;
}}
#canvas-container {{
    width: 100%; height: 100%; position: relative; overflow: hidden;
}}
svg {{ width: 100%; height: 100%; }}
canvas {{ width: 100%; height: 100%; }}

/* ── Layout Zones (use these for positioning) ── */
.zone-title {{ position:absolute; top:2%; left:0; width:100%; text-align:center; z-index:10; padding:0 5%; opacity:0; }}
.zone-subtitle {{ position:absolute; top:9%; left:0; width:100%; text-align:center; z-index:10; padding:0 5%; opacity:0; }}
.zone-main {{ position:absolute; top:16%; left:5%; width:90%; height:62%; display:flex; flex-direction:column; align-items:center; justify-content:flex-start; gap:0; overflow:hidden; }}
.zone-footer {{ position:absolute; bottom:2%; left:0; width:100%; text-align:center; z-index:10; padding:0 5%; opacity:0; }}
.zone-eq {{ position:absolute; top:10%; left:0; width:100%; text-align:center; z-index:10; opacity:0; }}
.zone-annotation {{ position:absolute; bottom:10%; left:0; width:100%; text-align:center; z-index:10; opacity:0; }}

/* ── Typography ── */
.title {{ font-size:clamp(1.3rem,2.5vw,2.2rem); font-weight:700; color:#e6edf3; letter-spacing:-0.02em; }}
.subtitle {{ font-size:clamp(0.9rem,1.6vw,1.3rem); font-weight:400; color:#8b949e; }}
.label {{ font-size:clamp(0.7rem,1.1vw,0.95rem); color:#8b949e; font-weight:500; }}
.mono {{ font-family:'JetBrains Mono','Fira Code','Cascadia Code',monospace; }}
.accent-blue {{ color:#58a6ff; }}
.accent-green {{ color:#3fb950; }}
.accent-red {{ color:#f85149; }}
.accent-yellow {{ color:#d29922; }}
.accent-purple {{ color:#bc8cff; }}

/* ── Array / List visualization ── */
.arr {{ display:flex; gap:3px; align-items:center; justify-content:center; flex-wrap:wrap; }}
.arr-cell {{
    display:flex; align-items:center; justify-content:center;
    min-width:clamp(30px,3.8vw,56px); height:clamp(30px,3.8vw,56px);
    background:#161b22; border:1.5px solid #30363d; border-radius:6px;
    color:#c9d1d9; font-size:clamp(0.65rem,1.1vw,0.95rem); font-weight:500;
    font-family:'JetBrains Mono','Fira Code',monospace;
}}
.arr-cell.hl {{ background:rgba(56,139,253,0.15); border-color:#388bfd; color:#58a6ff; }}
.arr-cell.found {{ background:rgba(63,185,80,0.15); border-color:#3fb950; color:#3fb950; }}
.arr-cell.dim {{ opacity:0.25; }}
.arr-cell.active {{ background:rgba(210,153,34,0.15); border-color:#d29922; color:#d29922; box-shadow:0 0 8px rgba(210,153,34,0.3); }}
.arr-idx {{ font-size:0.6rem; color:#484f58; position:absolute; bottom:-14px; font-family:'JetBrains Mono',monospace; }}

/* ── Pointer / marker ── */
.ptr {{
    display:flex; flex-direction:column; align-items:center; position:absolute; opacity:0;
}}
.ptr svg {{ width:16px; height:20px; }}
.ptr-label {{ font-size:0.7rem; font-weight:600; font-family:'JetBrains Mono',monospace; }}

/* ── Card / info box ── */
.card {{
    background:#161b22; border:1px solid #30363d; border-radius:10px;
    padding:clamp(10px,1.5vw,20px); color:#c9d1d9;
}}
.card-accent {{ border-left:3px solid #388bfd; }}

/* ── Tree node ── */
.tree-node {{
    display:flex; align-items:center; justify-content:center;
    width:clamp(32px,4vw,52px); height:clamp(32px,4vw,52px);
    background:#161b22; border:2px solid #30363d; border-radius:50%;
    color:#c9d1d9; font-size:clamp(0.7rem,1.1vw,0.9rem); font-weight:600;
    font-family:'JetBrains Mono',monospace; position:absolute;
}}
.tree-node.hl {{ border-color:#388bfd; color:#58a6ff; box-shadow:0 0 12px rgba(56,139,253,0.3); }}

/* ── Code block ── */
.code-box {{
    background:#0d1117; border:1px solid #30363d; border-radius:8px;
    padding:clamp(10px,1.5vw,20px); font-family:'JetBrains Mono',monospace;
    font-size:clamp(0.7rem,1vw,0.9rem); line-height:1.6; text-align:left;
    overflow:hidden; color:#c9d1d9;
}}
.code-line {{ white-space:pre; }}
.code-line.hl {{ background:rgba(56,139,253,0.1); border-left:2px solid #388bfd; padding-left:8px; margin-left:-10px; }}

/* ── KaTeX ── */
.katex {{ font-size:1.4em; }}
.katex-lg {{ font-size:1.8em; }}
.katex-xl {{ font-size:2.4em; }}

/* ── Progress / bar ── */
.bar {{
    height:clamp(20px,3vw,36px); background:#161b22; border-radius:6px;
    border:1px solid #30363d; overflow:hidden; position:relative;
}}
.bar-fill {{
    height:100%; border-radius:5px; transition:width 0.5s ease;
}}

/* ── Matrix / Grid ── */
.matrix-grid {{ display:grid; gap:2px; justify-content:center; }}
.matrix-cell {{
    display:flex; align-items:center; justify-content:center;
    min-width:clamp(28px,3.5vw,48px); height:clamp(28px,3.5vw,48px);
    background:#161b22; border:1px solid #30363d; border-radius:4px;
    color:#c9d1d9; font-size:clamp(0.6rem,1vw,0.85rem); font-weight:500;
    font-family:'JetBrains Mono','Fira Code',monospace;
}}
.matrix-cell.hl {{ background:rgba(56,139,253,0.15); border-color:#388bfd; color:#58a6ff; }}
.matrix-cell.fill {{ background:rgba(63,185,80,0.15); border-color:#3fb950; color:#3fb950; }}
.matrix-cell.active {{ background:rgba(210,153,34,0.15); border-color:#d29922; color:#d29922; }}
.matrix-cell.dim {{ opacity:0.25; }}
.matrix-label {{ font-size:0.65rem; color:#484f58; font-family:'JetBrains Mono',monospace; text-align:center; }}

/* ── Linked List ── */
.ll-node {{
    display:inline-flex; align-items:center; gap:0;
    background:#161b22; border:1.5px solid #30363d; border-radius:8px;
    color:#c9d1d9; font-family:'JetBrains Mono','Fira Code',monospace;
    font-size:clamp(0.7rem,1.1vw,0.95rem);
}}
.ll-node .ll-data {{ padding:8px 12px; border-right:1px solid #30363d; }}
.ll-node .ll-next {{ padding:8px 10px; color:#484f58; font-size:0.7rem; }}
.ll-node.hl {{ border-color:#388bfd; color:#58a6ff; box-shadow:0 0 12px rgba(56,139,253,0.3); }}
.ll-node.found {{ border-color:#3fb950; color:#3fb950; }}
.ll-arrow {{ color:#30363d; font-size:1.4rem; margin:0 4px; }}
.ll-null {{ color:#484f58; font-family:'JetBrains Mono',monospace; font-size:0.8rem; }}

/* ── Stack / Queue ── */
.stack-container {{
    display:flex; flex-direction:column-reverse; gap:2px;
    border:2px solid #30363d; border-top:none; border-radius:0 0 8px 8px;
    padding:4px; min-width:clamp(80px,10vw,140px);
}}
.queue-container {{
    display:flex; flex-direction:row; gap:2px;
    border:2px solid #30363d; border-radius:8px; padding:4px;
}}
.stack-item, .queue-item {{
    display:flex; align-items:center; justify-content:center;
    padding:8px 16px; background:#161b22; border-radius:4px;
    color:#c9d1d9; font-family:'JetBrains Mono','Fira Code',monospace;
    font-size:clamp(0.7rem,1.1vw,0.95rem);
}}
.stack-item.hl, .queue-item.hl {{ background:rgba(56,139,253,0.15); color:#58a6ff; }}
.stack-item.active, .queue-item.active {{ background:rgba(210,153,34,0.15); color:#d29922; }}

/* ── Graph ── */
.graph-node {{
    display:flex; align-items:center; justify-content:center;
    width:clamp(36px,4.5vw,56px); height:clamp(36px,4.5vw,56px);
    background:#161b22; border:2px solid #30363d; border-radius:50%;
    color:#c9d1d9; font-size:clamp(0.7rem,1.1vw,0.9rem); font-weight:600;
    font-family:'JetBrains Mono',monospace; position:absolute;
}}
.graph-node.visited {{ border-color:#3fb950; color:#3fb950; background:rgba(63,185,80,0.1); }}
.graph-node.current {{ border-color:#d29922; color:#d29922; box-shadow:0 0 12px rgba(210,153,34,0.4); }}
.graph-node.queued {{ border-color:#bc8cff; color:#bc8cff; }}
.graph-weight {{
    font-size:0.65rem; color:#8b949e; font-family:'JetBrains Mono',monospace;
    position:absolute; background:#0d1117; padding:1px 4px; border-radius:3px;
}}

/* ── Flowchart ── */
.flow-box {{
    display:flex; align-items:center; justify-content:center;
    padding:10px 20px; background:#161b22; border:1.5px solid #30363d;
    border-radius:8px; color:#c9d1d9; font-size:clamp(0.7rem,1vw,0.9rem);
    position:absolute; white-space:nowrap;
}}
.flow-box.start, .flow-box.end {{ border-radius:24px; }}
.flow-diamond {{
    display:flex; align-items:center; justify-content:center;
    width:clamp(70px,9vw,110px); height:clamp(70px,9vw,110px);
    background:#161b22; border:1.5px solid #d29922;
    transform:rotate(45deg); position:absolute;
}}
.flow-diamond span {{ transform:rotate(-45deg); font-size:clamp(0.55rem,0.8vw,0.75rem); color:#d29922; text-align:center; }}
.flow-box.hl {{ border-color:#388bfd; box-shadow:0 0 12px rgba(56,139,253,0.3); }}

/* ── Neural Network ── */
.nn-neuron {{
    display:flex; align-items:center; justify-content:center;
    width:clamp(24px,3vw,40px); height:clamp(24px,3vw,40px);
    background:#161b22; border:2px solid #30363d; border-radius:50%;
    color:#c9d1d9; font-size:0.55rem; position:absolute;
    font-family:'JetBrains Mono',monospace;
}}
.nn-neuron.active {{ border-color:#58a6ff; background:rgba(56,139,253,0.2); box-shadow:0 0 10px rgba(56,139,253,0.3); }}
.nn-neuron.fired {{ border-color:#3fb950; background:rgba(63,185,80,0.2); }}
.nn-neuron.input {{ border-color:#d29922; }}
.nn-neuron.output {{ border-color:#bc8cff; }}
.nn-label {{ font-size:clamp(0.6rem,0.9vw,0.8rem); color:#8b949e; text-align:center; font-weight:500; }}

/* ── Convolution ── */
.conv-grid {{ display:inline-grid; gap:1px; }}
.conv-cell {{
    display:flex; align-items:center; justify-content:center;
    min-width:clamp(28px,3vw,44px); height:clamp(28px,3vw,44px);
    background:#161b22; border:1px solid #30363d; border-radius:3px;
    color:#c9d1d9; font-size:0.65rem; font-family:'JetBrains Mono',monospace;
}}
.conv-kernel {{
    position:absolute; border:2.5px solid #d29922; border-radius:4px;
    background:rgba(210,153,34,0.08); pointer-events:none; z-index:5;
}}
.conv-cell.active {{ background:rgba(210,153,34,0.2); border-color:#d29922; }}
.conv-cell.output {{ background:rgba(63,185,80,0.15); border-color:#3fb950; color:#3fb950; }}

/* ── Heatmap ── */
.hm-grid {{ display:grid; gap:1px; justify-content:center; }}
.hm-cell {{
    display:flex; align-items:center; justify-content:center;
    min-width:clamp(24px,3vw,40px); height:clamp(24px,3vw,40px);
    border-radius:3px; font-size:0.6rem; font-family:'JetBrains Mono',monospace;
    color:#e6edf3;
}}

/* ── Comparison ── */
.compare-container {{ display:flex; gap:20px; width:100%; height:100%; align-items:stretch; }}
.compare-panel {{
    flex:1; background:#161b22; border:1px solid #30363d; border-radius:10px;
    padding:clamp(10px,1.5vw,20px); display:flex; flex-direction:column;
    align-items:center; gap:10px; overflow:hidden;
}}
.compare-divider {{ width:2px; background:#30363d; align-self:stretch; }}
.compare-label {{
    font-size:clamp(0.8rem,1.2vw,1rem); font-weight:600; color:#8b949e;
    text-transform:uppercase; letter-spacing:0.05em;
}}

/* ── Arrow / Connection SVG layer ── */
.arrow-layer {{
    position:absolute; top:0; left:0; width:100%; height:100%;
    pointer-events:none; z-index:5; overflow:visible;
}}
.arrow-layer line, .arrow-layer path {{
    fill:none; stroke-linecap:round; stroke-linejoin:round;
}}

/* ── Utility ── */
.hidden {{ opacity:0; }}
.center-abs {{ position:absolute; left:50%; top:50%; transform:translate(-50%,-50%); }}
.glow-blue {{ box-shadow:0 0 16px rgba(56,139,253,0.4); }}
.glow-green {{ box-shadow:0 0 16px rgba(63,185,80,0.4); }}
.glow-yellow {{ box-shadow:0 0 16px rgba(210,153,34,0.4); }}
.glow-purple {{ box-shadow:0 0 16px rgba(188,140,255,0.4); }}
</style>
</head>
<body>
<div id="canvas-container">
{content_html}
</div>
<script>
// ── GSAP Master Timeline ──
const tl = gsap.timeline({{ paused: true }});

// ── Helper: resolve D3 selections to DOM elements for GSAP ──
function _t(el) {{ return el && typeof el.node === 'function' ? el.node() : el; }}

// ── Animation API (available immediately) ──
window.animationAPI = {{
    timeline: tl,
    seekToStep(label) {{ tl.seek(label); tl.pause(); }},
    play() {{ tl.play(); }},
    pause() {{ tl.pause(); }},
    getSteps() {{ return Object.keys(tl.labels); }},
    getCurrentStep() {{
        const t = tl.time();
        let current = '';
        for (const [name, time] of Object.entries(tl.labels)) {{
            if (time <= t) current = name;
        }}
        return current;
    }},
    onStepChange(cb) {{ this._cb = cb; }},
    _cb: null,
}};

// ── Step change notifier ──
let _lastStep = '';
function _notifyStepChange() {{
    const s = window.animationAPI.getCurrentStep();
    if (s !== _lastStep) {{
        _lastStep = s;
        if (window.animationAPI._cb) window.animationAPI._cb(s);
        window.parent.postMessage({{ event: 'stepChanged', label: s }}, '*');
    }}
    requestAnimationFrame(_notifyStepChange);
}}
_notifyStepChange();

// ── Listen for parent commands ──
window.addEventListener('message', (e) => {{
    const {{ action, label }} = e.data || {{}};
    if (!action) return;
    const _d = tl.duration ? tl.duration() : 0;
    const _t = tl.time ? tl.time() : 0;
    const _n = Object.keys(tl.labels || {{}}).length;
    console.log(`[AnimFrame] ${{action}} ${{label||''}} dur=${{_d.toFixed(1)}} t=${{_t.toFixed(1)}} labels=${{_n}}`);
    if (action === 'seekToStep') {{
        _lastStep = '';
        window.animationAPI.seekToStep(label);
    }}
    else if (action === 'play') window.animationAPI.play();
    else if (action === 'pause') window.animationAPI.pause();
    else if (action === 'queryLabels') {{
        window.parent.postMessage({{
            event: 'labelsResponse',
            labels: Object.keys(tl.labels || {{}}),
            labelTimes: tl.labels || {{}},
            duration: _d,
        }}, '*');
    }}
}});

// ── Pre-generated images (base64, keyed by step label) ──
const __images = {image_data};

// ══════════════════════════════════════════════════════════
// ── ANIMATION CODE (generated by Claude) ──
// ══════════════════════════════════════════════════════════
{animation_js}

// ── DO NOT auto-play. The teacher controls all playback via postMessage. ──
// The classroom's lockstep engine seeks to each step and tweens between
// them, so the timeline must stay paused at t=0 until commanded otherwise.
tl.pause();
tl.seek(0);

// ── Signal ready to parent with label info ──
window.parent.postMessage({{
    event: 'iframeReady',
    labels: Object.keys(tl.labels || {{}}),
    labelTimes: tl.labels || {{}},
    duration: tl.duration ? tl.duration() : 0,
}}, '*');
</script>
</body>
</html>
"""


VIDEO_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #0d1117; color: #c9d1d9;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    width: 100vw; height: 100vh; overflow: hidden;
    display: flex; align-items: center; justify-content: center;
}}
video {{
    max-width: 100%; max-height: 100%; object-fit: contain;
}}
</style>
</head>
<body>
<video id="player" src="{video_url}" preload="auto"></video>
<script>
// ── Video Player ──
const video = document.getElementById('player');
const stepMap = {step_map_json};

// ── Animation API (same interface as browser template) ──
window.animationAPI = {{
    seekToStep(label) {{
        const t = stepMap[label];
        if (t !== undefined) {{ video.currentTime = t; video.pause(); }}
    }},
    play() {{ video.play(); }},
    pause() {{ video.pause(); }},
    getSteps() {{ return Object.keys(stepMap); }},
    getCurrentStep() {{
        const t = video.currentTime;
        let current = '';
        for (const [name, time] of Object.entries(stepMap)) {{
            if (time <= t) current = name;
        }}
        return current;
    }},
    onStepChange(cb) {{ this._cb = cb; }},
    _cb: null,
}};

// ── Step change notifier ──
let _lastStep = '';
function _notifyStepChange() {{
    const s = window.animationAPI.getCurrentStep();
    if (s !== _lastStep) {{
        _lastStep = s;
        if (window.animationAPI._cb) window.animationAPI._cb(s);
        window.parent.postMessage({{ event: 'stepChanged', label: s }}, '*');
    }}
    requestAnimationFrame(_notifyStepChange);
}}
_notifyStepChange();

// ── Listen for parent commands ──
window.addEventListener('message', (e) => {{
    const {{ action, label }} = e.data || {{}};
    if (!action) return;
    const _n = Object.keys(stepMap || {{}}).length;
    console.log(`[AnimFrame:video] ${{action}} ${{label||''}} t=${{video.currentTime.toFixed(1)}} steps=${{_n}}`);
    if (action === 'seekToStep') window.animationAPI.seekToStep(label);
    else if (action === 'play') window.animationAPI.play();
    else if (action === 'pause') window.animationAPI.pause();
}});

// ── DO NOT auto-play. The teacher controls all playback via postMessage. ──
// The classroom's lockstep engine seeks to each step and tweens between
// them, so the video must stay paused at t=0 until commanded otherwise.
video.pause();
video.currentTime = 0;
</script>
</body>
</html>
"""
