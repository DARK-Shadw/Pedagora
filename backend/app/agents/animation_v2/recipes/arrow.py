"""Recipe: Arrow / Connection — SVG arrows between DOM elements, weighted flows, directed edges."""

ID = "arrow"

KEYWORDS = [
    "arrow", "connection", "flow", "directed", "pointer",
    "weighted arrow", "edge", "link between", "connects to",
    "data flow", "signal flow", "forward pass", "backward pass",
    "attention flow", "weighted sum", "weighted output",
    "dependency", "pipeline", "call graph", "reference",
    "maps to", "points to", "feeds into",
]

CSS_DOCS = """\
ARROW / CONNECTION COMPONENTS:
  .arrow-layer   — SVG overlay (absolute, 100%×100%, pointer-events:none, z-index:5)
                   Place inside a position:relative container.
                   Lines/paths inside have fill:none, round caps/joins.
  Arrowhead markers are defined per-SVG via <defs>.
  Arrows connect DOM elements using getBoundingClientRect() for pixel coords."""

PATTERN = """\
ARROWS / CONNECTIONS (SVG arrows between DOM elements):

  === SETUP: SVG arrow layer inside a positioned container ===

  // The container must be position:relative so the SVG overlay aligns.
  // Create a wrapper for both your elements and the arrow SVG:
  const arrowScene = document.createElement('div');
  arrowScene.style.cssText = 'position:relative; width:100%;';
  mainZone.appendChild(arrowScene);

  // Create the SVG overlay (fills the container, sits on top):
  const arrowSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  arrowSvg.classList.add('arrow-layer');
  arrowScene.appendChild(arrowSvg);

  // Define arrowhead markers (one per color you need):
  arrowSvg.innerHTML = `
    <defs>
      <marker id="ah-blue" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
        <polygon points="0 0, 8 3, 0 6" fill="#58a6ff"/>
      </marker>
      <marker id="ah-green" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
        <polygon points="0 0, 8 3, 0 6" fill="#3fb950"/>
      </marker>
      <marker id="ah-yellow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
        <polygon points="0 0, 8 3, 0 6" fill="#d29922"/>
      </marker>
      <marker id="ah-red" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
        <polygon points="0 0, 8 3, 0 6" fill="#f85149"/>
      </marker>
      <marker id="ah-purple" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
        <polygon points="0 0, 8 3, 0 6" fill="#bc8cff"/>
      </marker>
    </defs>`;

  === CONNECTING TWO DOM ELEMENTS (pixel-precise) ===

  // Helper: get center of a DOM element relative to the arrowScene container
  function getCenter(el) {{
    const r = el.getBoundingClientRect();
    const s = arrowScene.getBoundingClientRect();
    return {{ x: r.left - s.left + r.width/2, y: r.top - s.top + r.height/2 }};
  }}

  // Helper: get edge point (connect from bottom of source, top of target, etc.)
  function getEdge(el, side) {{
    // side: 'top', 'bottom', 'left', 'right'
    const r = el.getBoundingClientRect();
    const s = arrowScene.getBoundingClientRect();
    const cx = r.left - s.left + r.width/2;
    const cy = r.top - s.top + r.height/2;
    if (side === 'top')    return {{ x: cx, y: r.top - s.top }};
    if (side === 'bottom') return {{ x: cx, y: r.bottom - s.top }};
    if (side === 'left')   return {{ x: r.left - s.left, y: cy }};
    if (side === 'right')  return {{ x: r.right - s.left, y: cy }};
    return {{ x: cx, y: cy }};
  }}

  // Draw a straight arrow from sourceEl to targetEl:
  function drawArrow(sourceEl, targetEl, opts) {{
    // opts: {{ color, width, fromSide, toSide, markerId, className }}
    const from = getEdge(sourceEl, opts.fromSide || 'bottom');
    const to   = getEdge(targetEl, opts.toSide || 'top');
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', from.x);
    line.setAttribute('y1', from.y);
    line.setAttribute('x2', to.x);
    line.setAttribute('y2', to.y);
    line.setAttribute('stroke', opts.color || '#58a6ff');
    line.setAttribute('stroke-width', opts.width || 2);
    if (opts.markerId) line.setAttribute('marker-end', `url(#${{opts.markerId}})`);
    line.setAttribute('opacity', '0');
    arrowSvg.appendChild(line);
    return line;
  }}

  // Draw a curved arrow (quadratic bezier) — good for avoiding overlaps:
  function drawCurvedArrow(sourceEl, targetEl, opts) {{
    const from = getEdge(sourceEl, opts.fromSide || 'bottom');
    const to   = getEdge(targetEl, opts.toSide || 'top');
    const cx = (from.x + to.x) / 2 + (opts.curveOffset || 0);
    const cy = (from.y + to.y) / 2 + (opts.curveOffset || 30);
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', `M ${{from.x}} ${{from.y}} Q ${{cx}} ${{cy}} ${{to.x}} ${{to.y}}`);
    path.setAttribute('stroke', opts.color || '#58a6ff');
    path.setAttribute('stroke-width', opts.width || 2);
    if (opts.markerId) path.setAttribute('marker-end', `url(#${{opts.markerId}})`);
    path.setAttribute('opacity', '0');
    arrowSvg.appendChild(path);
    return path;
  }}

  === WEIGHTED ARROWS (thickness = importance) ===

  // Draw multiple arrows with varying thickness based on weights:
  const weights = [0.05, 0.10, 0.45, 0.40];
  const sources = [tokenEl0, tokenEl1, tokenEl2, tokenEl3];
  const target = outputEl;
  const arrowLines = weights.map((w, i) => {{
    return drawArrow(sources[i], target, {{
      color: w > 0.3 ? '#f85149' : w > 0.1 ? '#d29922' : '#388bfd',
      width: Math.max(1.5, w * 8),
      fromSide: 'bottom',
      toSide: 'top',
      markerId: w > 0.3 ? 'ah-red' : w > 0.1 ? 'ah-yellow' : 'ah-blue',
    }});
  }});

  // Animate arrows in with stagger, thicker ones more prominent:
  gsap.set(arrowLines, {{opacity:0}});
  tl.to(arrowLines, {{opacity:0.8, duration:0.5, stagger:0.15}}, 'show-arrows');

  === FAN-OUT PATTERN (one source → many targets) ===

  // Arrows from one element to several targets:
  const fanArrows = targetEls.map((t, i) => {{
    return drawArrow(sourceEl, t, {{
      color: colors[i],
      width: 2,
      fromSide: 'bottom',
      toSide: 'top',
      markerId: 'ah-blue',
    }});
  }});

  === FAN-IN PATTERN (many sources → one target) ===

  // Arrows from several elements into one:
  const mergeArrows = sourceEls.map((s, i) => {{
    return drawArrow(s, targetEl, {{
      color: '#58a6ff',
      width: weights[i] * 6,
      fromSide: 'bottom',
      toSide: 'top',
      markerId: 'ah-blue',
    }});
  }});

  === ANIMATING ARROWS ===

  // Fade in one by one:
  tl.to(arrowLines, {{opacity:0.8, duration:0.4, stagger:0.1}}, 'label');

  // Pulse/highlight a specific arrow:
  tl.to(arrowLines[2], {{strokeWidth:6, duration:0.3}}, 'label+=1');

  // Color change:
  tl.to(arrowLines[0], {{stroke:'#3fb950', duration:0.5}}, 'label+=2');

  // IMPORTANT: arrows use SVG attributes, not CSS properties.
  // Use tl.to(line, {{attr:{{strokeWidth:4}}}}) if direct property doesn't work.

  === KEY RULES FOR ARROWS ===

  1. ALWAYS use a position:relative container + absolute SVG overlay.
     Using hardcoded pixel coordinates breaks on different viewports.
  2. Source and target elements for arrows MUST be inside the same arrowScene container.
     Put both the source elements, target elements, AND the SVG in arrowScene.
     If arrows connect elements in a previous step, those elements must NOT be
     collapsed (height:0) — keep them visible or re-create them inside arrowScene.
  3. Call getBoundingClientRect() inside tl.call() at the step where arrows appear,
     NOT during DOM setup. Elements may not have final layout during setup:
       tl.call(() => {{
         sourceEls.forEach((src, i) => {{
           const line = drawArrow(src, targetEl, {{ ... }});
           gsap.set(line, {{opacity:0}});
           gsap.to(line, {{opacity:0.8, duration:0.5, delay:i*0.15}});
         }});
       }}, null, 'arrow-step+=0.5');
  4. Set arrow opacity to 0 initially, reveal with tl.to({{opacity:0.8}}).
     Don't use full opacity 1.0 — arrows at 0.7-0.8 look cleaner over content.
  5. For weighted arrows, map weight → stroke-width AND color intensity.
     Thin+dim for low weights, thick+bright for high weights.
  6. Prefer straight lines for simple connections, curved for overlapping paths.
  7. The arrow step should COLLAPSE all previous-step content that isn't part of
     the arrow visualization. Only keep elements that arrows connect to."""
