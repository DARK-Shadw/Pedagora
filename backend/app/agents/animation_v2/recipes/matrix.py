"""Recipe: Matrix — 2D grids, DP tables, confusion matrices, transition tables."""

ID = "matrix"

KEYWORDS = [
    "matrix", "2d grid", "2d array", "dp table", "dynamic programming",
    "memoization", "tabulation", "confusion matrix", "transition matrix",
    "adjacency matrix", "matrix multiplication", "determinant", "transpose",
    "lcs", "knapsack", "edit distance", "floyd", "warshall",
]

CSS_DOCS = """\
MATRIX / GRID COMPONENTS:
  .matrix-grid   — CSS grid container (centered, auto gap)
  .matrix-cell   — styled cell (dark bg, monospace, auto-scales)
  .matrix-cell.hl — blue highlight (current cell)
  .matrix-cell.fill — green (computed/filled value)
  .matrix-cell.active — yellow (cell being computed)
  .matrix-cell.dim — faded (not yet computed)
  .matrix-label  — small monospace label for row/col headers"""

PATTERN = """\
MATRIX / 2D GRID (DP tables, confusion matrices, adjacency matrices):
  const rows = 5, cols = 5;
  const gridEl = document.createElement('div');
  gridEl.className = 'matrix-grid';
  gridEl.style.gridTemplateColumns = `repeat(${{cols}}, 1fr)`;

  const grid = [];
  for (let r = 0; r < rows; r++) {{
    grid[r] = [];
    for (let c = 0; c < cols; c++) {{
      const cell = document.createElement('div');
      cell.className = 'matrix-cell';
      cell.textContent = '—';  // placeholder
      gridEl.appendChild(cell);
      grid[r][c] = cell;
    }}
  }}
  mainZone.appendChild(gridEl);
  gsap.set(gridEl, {{opacity:0}});

  // Row/column headers (place above grid and to the left)
  const colHeaders = document.createElement('div');
  colHeaders.className = 'matrix-grid';
  colHeaders.style.gridTemplateColumns = `repeat(${{cols}}, 1fr)`;
  colHeaders.style.marginBottom = '4px';
  for (let c = 0; c < cols; c++) {{
    const h = document.createElement('div');
    h.className = 'matrix-label';
    h.textContent = c;
    colHeaders.appendChild(h);
  }}
  mainZone.insertBefore(colHeaders, gridEl);

  // DP fill pattern — highlight row, col, then fill cell:
  tl.to(grid[r][c], {{borderColor:'#d29922', duration:0.3}}, 'fill-step');
  tl.call(() => {{ grid[r][c].textContent = value; }}, null, 'fill-step+=0.4');
  tl.to(grid[r][c], {{borderColor:'#3fb950', color:'#3fb950', duration:0.3}}, 'fill-step+=0.5');

  // Highlight entire row or column:
  const rowCells = grid[r];  // array of cells in row r
  tl.to(rowCells, {{backgroundColor:'rgba(56,139,253,0.1)', duration:0.3, stagger:0.05}}, 'label');

  // Trace back path (for DP backtracking visualization):
  tl.to(grid[r][c], {{boxShadow:'0 0 12px rgba(63,185,80,0.4)', scale:1.05, duration:0.4}}, 'trace+=0.5');"""
