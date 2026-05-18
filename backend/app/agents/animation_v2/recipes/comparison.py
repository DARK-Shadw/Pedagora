"""Recipe: Comparison — side-by-side panels, before/after, algorithm comparison."""

ID = "comparison"

KEYWORDS = [
    "comparison", "compare", "versus", "vs", "side by side",
    "before after", "before and after", "difference", "trade-off",
    "tradeoff", "pros cons", "advantage", "disadvantage",
    "time complexity", "space complexity", "benchmark", "performance",
    "o(n)", "o(log n)", "o(n^2)", "big o",
    "brute force", "optimized",
]

CSS_DOCS = """\
COMPARISON COMPONENTS:
  .compare-container — flex container for side-by-side panels
  .compare-panel     — individual panel (dark bg, rounded, flex-column)
  .compare-divider   — vertical separator line between panels
  .compare-label     — uppercase label for each panel (muted color)"""

PATTERN = """\
COMPARISON (side-by-side panels showing two approaches/states):
  const compareWrap = document.createElement('div');
  compareWrap.className = 'compare-container';
  mainZone.appendChild(compareWrap);

  // Left panel
  const leftPanel = document.createElement('div');
  leftPanel.className = 'compare-panel';
  const leftLabel = document.createElement('div');
  leftLabel.className = 'compare-label accent-red';
  leftLabel.textContent = 'Brute Force';
  leftPanel.appendChild(leftLabel);
  compareWrap.appendChild(leftPanel);

  // Divider
  const divider = document.createElement('div');
  divider.className = 'compare-divider';
  compareWrap.appendChild(divider);

  // Right panel
  const rightPanel = document.createElement('div');
  rightPanel.className = 'compare-panel';
  const rightLabel = document.createElement('div');
  rightLabel.className = 'compare-label accent-green';
  rightLabel.textContent = 'Optimized';
  rightPanel.appendChild(rightLabel);
  compareWrap.appendChild(rightPanel);

  // Add content to each panel (arrays, charts, metrics, etc.)
  // Example: complexity badges
  function makeMetric(label, value, color, parent) {{
    const metric = document.createElement('div');
    metric.className = 'card';
    metric.style.cssText = 'padding:10px 16px; text-align:center; width:100%;';
    metric.innerHTML = `<div class="label">${{label}}</div>` +
      `<div class="mono" style="font-size:1.2rem; color:${{color}}; margin-top:4px;">${{value}}</div>`;
    parent.appendChild(metric);
    return metric;
  }}

  const m1 = makeMetric('Time', 'O(n²)', '#f85149', leftPanel);
  const m2 = makeMetric('Space', 'O(1)', '#8b949e', leftPanel);
  const m3 = makeMetric('Time', 'O(n log n)', '#3fb950', rightPanel);
  const m4 = makeMetric('Space', 'O(n)', '#d29922', rightPanel);

  gsap.set(compareWrap, {{opacity:0}});
  gsap.set([m1, m2, m3, m4], {{opacity:0, y:15}});

  // Reveal panels:
  tl.to(compareWrap, {{opacity:1, duration:0.8}}, 'show-compare');
  tl.to([m1, m2], {{opacity:1, y:0, duration:0.5, stagger:0.2}}, 'show-left');
  tl.to([m3, m4], {{opacity:1, y:0, duration:0.5, stagger:0.2}}, 'show-right');

  // Highlight winner:
  tl.to(rightPanel, {{borderColor:'#3fb950', boxShadow:'0 0 16px rgba(63,185,80,0.3)', duration:0.6}}, 'winner');

  // You can put arrays, code blocks, or charts inside each panel
  // just like in other recipes — the panel is a flex-column container."""
