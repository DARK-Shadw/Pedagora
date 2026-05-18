"""Recipe: Array — sorted lists, search spaces, element comparison, swapping."""

ID = "array"

KEYWORDS = [
    "array", "sorted", "list", "cells", "elements", "indices", "index",
    "binary search", "linear search", "search space", "partition",
    "swap", "bubble sort", "insertion sort", "selection sort", "merge sort",
    "quick sort", "sorting", "two pointer", "sliding window", "subarray",
    "subsequence", "kadane", "dutch flag", "rotate",
]

CSS_DOCS = """\
ARRAY COMPONENTS:
  .arr           — flex container for array cells (centered, wraps)
  .arr-cell      — styled cell (dark bg, rounded, monospace, min-width auto-scales)
  .arr-cell.hl   — blue highlight (current comparison)
  .arr-cell.found — green highlight (target found / sorted position)
  .arr-cell.dim  — faded out (eliminated from search)
  .arr-cell.active — yellow glow (current element being processed)
  .ptr           — pointer marker container (absolute positioned)
  .ptr-label     — pointer label text (monospace, small)"""

PATTERN = """\
ARRAY (sorted lists, search spaces, element visualization):
  const arrWrap = document.createElement('div');
  arrWrap.className = 'arr';
  const data = [3, 7, 12, 18, 22, 27, 31, 38, 42];
  const cells = data.map(v => {{
    const cell = document.createElement('div');
    cell.className = 'arr-cell';
    cell.textContent = v;
    arrWrap.appendChild(cell);
    return cell;
  }});
  mainZone.appendChild(arrWrap);

  // Index labels (same flex layout for perfect alignment)
  const idxRow = document.createElement('div');
  idxRow.className = 'arr';
  idxRow.style.marginTop = '4px';
  data.forEach((_, i) => {{
    const idx = document.createElement('div');
    idx.className = 'label mono';
    idx.textContent = i;
    idx.style.cssText = 'min-width:clamp(30px,3.8vw,56px); text-align:center;';
    idxRow.appendChild(idx);
  }});
  mainZone.appendChild(idxRow);

  // Hide then stagger-reveal at a label:
  gsap.set(cells, {{opacity:0, y:15}});
  tl.to(cells, {{opacity:1, y:0, duration:0.4, stagger:0.08}}, 'show-array+=0.5');

POINTER ROW (low/mid/high markers aligned under array cells):
  // Same flex layout as array — one slot per cell, pointer goes in its slot
  const ptrRow = document.createElement('div');
  ptrRow.className = 'arr';
  ptrRow.style.marginTop = '6px';
  const ptrSlots = data.map(() => {{
    const slot = document.createElement('div');
    slot.style.cssText = 'min-width:clamp(30px,3.8vw,56px); height:36px; display:flex; flex-direction:column; align-items:center;';
    ptrRow.appendChild(slot);
    return slot;
  }});
  mainZone.appendChild(ptrRow);

  // Helper to create a pointer label
  function makePtr(text, color) {{
    const el = document.createElement('div');
    el.style.cssText = `display:flex;flex-direction:column;align-items:center;color:${{color}};`;
    el.innerHTML = `<div style="font-size:1em;">&#9650;</div><div class="mono" style="font-size:0.65rem;">${{text}}</div>`;
    return el;
  }}
  const lowEl = makePtr('low', '#58a6ff');
  const highEl = makePtr('high', '#f85149');
  ptrSlots[0].appendChild(lowEl);
  ptrSlots[9].appendChild(highEl);
  gsap.set([lowEl, highEl], {{opacity:0}});

  // Move pointer from slot 4 to slot 7 (fade out, reparent, fade in):
  tl.to(midEl, {{opacity:0, duration:0.2}}, 'narrow-right');
  tl.call(() => {{ ptrSlots[7].appendChild(midEl); }}, null, 'narrow-right+=0.3');
  tl.to(midEl, {{opacity:1, duration:0.3}}, 'narrow-right+=0.3');

SWAP (animate two cells exchanging positions — for sorting):
  // Use GSAP flip or manual x-offset swap
  const cellW = cells[0].getBoundingClientRect().width + 3; // cell width + gap
  tl.to(cells[i], {{x: `+=${{cellW}}`, duration:0.5, ease:'power2.inOut'}}, 'swap+=0.5');
  tl.to(cells[j], {{x: `-=${{cellW}}`, duration:0.5, ease:'power2.inOut'}}, '<');
  // After animation, swap DOM order with tl.call:
  tl.call(() => {{ arrWrap.insertBefore(cells[j], cells[i]); }}, null, 'swap+=1.2');"""
