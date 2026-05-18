"""Recipe: Heatmap — color-coded grids, attention maps, confusion matrices, intensity."""

ID = "heatmap"

KEYWORDS = [
    "heatmap", "heat map", "attention", "attention map", "attention weight",
    "self-attention", "cross-attention", "confusion matrix", "correlation",
    "intensity", "color map", "color coded", "gradient map",
    "activation map", "saliency", "feature importance",
]

CSS_DOCS = """\
HEATMAP COMPONENTS:
  .hm-grid       — CSS grid container (tight gap, centered)
  .hm-cell       — individual cell (small, monospace for values)
  Color is applied via inline backgroundColor — no preset color classes.
  Use rgba with varying alpha or a color scale for intensity."""

PATTERN = """\
HEATMAP (color-coded grid showing intensity values):
  const hmContainer = document.createElement('div');
  hmContainer.style.cssText = 'display:flex; flex-direction:column; align-items:center; gap:10px;';
  mainZone.appendChild(hmContainer);

  // Color scale helper (value 0-1 → color)
  function heatColor(value) {{
    // Blue (cold) → Yellow → Red (hot)
    if (value < 0.5) {{
      const t = value * 2;
      return `rgb(${{Math.round(56 + t*152)}}, ${{Math.round(139 - t*39)}}, ${{Math.round(253 - t*204)}})`;
    }} else {{
      const t = (value - 0.5) * 2;
      return `rgb(${{Math.round(208 + t*40)}}, ${{Math.round(100 - t*67)}}, ${{Math.round(49 + t*24)}})`;
    }}
  }}

  // Row/column labels
  const rowLabels = ['Query 1', 'Query 2', 'Query 3', 'Query 4'];
  const colLabels = ['Key 1', 'Key 2', 'Key 3', 'Key 4'];

  // Column header row
  const colHeaderRow = document.createElement('div');
  colHeaderRow.style.cssText = 'display:flex; gap:1px; margin-left:80px;';
  colLabels.forEach(label => {{
    const h = document.createElement('div');
    h.className = 'label mono';
    h.textContent = label;
    h.style.cssText = 'min-width:clamp(40px,5vw,60px); text-align:center; font-size:0.6rem;';
    colHeaderRow.appendChild(h);
  }});
  hmContainer.appendChild(colHeaderRow);

  // Build grid with row labels
  const rows = 4, cols = 4;
  const hmData = [
    [0.9, 0.1, 0.3, 0.05],
    [0.2, 0.8, 0.1, 0.15],
    [0.1, 0.3, 0.7, 0.2],
    [0.05, 0.1, 0.2, 0.85],
  ];
  const hmCells = [];
  for (let r = 0; r < rows; r++) {{
    hmCells[r] = [];
    const rowDiv = document.createElement('div');
    rowDiv.style.cssText = 'display:flex; align-items:center; gap:1px;';

    // Row label
    const rLabel = document.createElement('div');
    rLabel.className = 'label mono';
    rLabel.textContent = rowLabels[r];
    rLabel.style.cssText = 'width:80px; text-align:right; padding-right:8px; font-size:0.6rem;';
    rowDiv.appendChild(rLabel);

    for (let c = 0; c < cols; c++) {{
      const cell = document.createElement('div');
      cell.className = 'hm-cell';
      cell.style.cssText = `min-width:clamp(40px,5vw,60px); height:clamp(40px,5vw,60px);`;
      cell.textContent = hmData[r][c].toFixed(2);
      // Start with neutral color, animate to heat color
      cell.style.backgroundColor = '#161b22';
      hmCells[r][c] = cell;
      rowDiv.appendChild(cell);
    }}
    hmContainer.appendChild(rowDiv);
  }}

  gsap.set(hmContainer, {{opacity:0}});

  // Reveal grid:
  tl.to(hmContainer, {{opacity:1, duration:0.8}}, 'show-heatmap');

  // Animate cells filling with color (row by row or all at once):
  for (let r = 0; r < rows; r++) {{
    for (let c = 0; c < cols; c++) {{
      const color = heatColor(hmData[r][c]);
      const delay = r * 0.3 + c * 0.08;
      tl.to(hmCells[r][c], {{backgroundColor: color, duration:0.4}}, `fill-heatmap+=${{delay}}`);
    }}
  }}

  // Highlight max attention (diagonal in self-attention):
  tl.to(hmCells[0][0], {{boxShadow:'0 0 12px rgba(248,81,73,0.5)', scale:1.1, duration:0.5}}, 'highlight-max');

  // Legend
  const legend = document.createElement('div');
  legend.style.cssText = 'display:flex; align-items:center; gap:8px; margin-top:8px;';
  legend.innerHTML = '<span class="label" style="color:#58a6ff;">0.0 (cold)</span>' +
    '<div style="width:120px; height:12px; border-radius:6px; background:linear-gradient(to right, #388bfd, #d29922, #f85149);"></div>' +
    '<span class="label" style="color:#f85149;">1.0 (hot)</span>';
  hmContainer.appendChild(legend);
  gsap.set(legend, {{opacity:0}});
  tl.to(legend, {{opacity:1, duration:0.5}}, 'show-legend');"""
