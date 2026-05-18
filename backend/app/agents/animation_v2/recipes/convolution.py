"""Recipe: Convolution — sliding kernel, feature maps, pooling, CNN visualization."""

ID = "convolution"

KEYWORDS = [
    "convolution", "convolutional", "cnn", "kernel", "filter",
    "feature map", "pooling", "max pool", "average pool", "stride",
    "padding", "channel", "receptive field", "conv2d", "conv1d",
    "image recognition", "image classification", "object detection",
    "feature extraction", "sliding window",
]

CSS_DOCS = """\
CONVOLUTION COMPONENTS:
  .conv-grid     — inline CSS grid for input/output matrices
  .conv-cell     — cell in convolution grid (monospace, small)
  .conv-kernel   — overlay border showing kernel position (absolute, yellow border)
  .conv-cell.active — yellow highlight (cells under kernel)
  .conv-cell.output — green highlight (computed output cell)"""

PATTERN = """\
CONVOLUTION (sliding kernel over input grid, producing output feature map):
  // Layout: Input Grid | Kernel | Output Grid (side by side)
  const convLayout = document.createElement('div');
  convLayout.style.cssText = 'display:flex; align-items:center; justify-content:center; gap:30px; width:100%;';
  mainZone.appendChild(convLayout);

  // Input grid (e.g., 5x5)
  const inputSize = 5;
  const inputWrap = document.createElement('div');
  inputWrap.style.cssText = 'display:flex; flex-direction:column; align-items:center; gap:6px;';
  const inputLabel = document.createElement('div');
  inputLabel.className = 'label';
  inputLabel.textContent = 'Input (5×5)';
  inputWrap.appendChild(inputLabel);

  const inputGridEl = document.createElement('div');
  inputGridEl.className = 'conv-grid';
  inputGridEl.style.cssText = `grid-template-columns:repeat(${{inputSize}},1fr); position:relative;`;
  const inputCells = [];
  const inputData = [
    [1,0,1,0,1],[0,1,0,1,0],[1,1,1,0,0],[0,0,1,1,1],[1,0,0,1,0]
  ];
  for (let r = 0; r < inputSize; r++) {{
    inputCells[r] = [];
    for (let c = 0; c < inputSize; c++) {{
      const cell = document.createElement('div');
      cell.className = 'conv-cell';
      cell.textContent = inputData[r][c];
      inputGridEl.appendChild(cell);
      inputCells[r][c] = cell;
    }}
  }}
  inputWrap.appendChild(inputGridEl);
  convLayout.appendChild(inputWrap);

  // Kernel overlay (positioned over input grid)
  const kernelSize = 3;
  const kernelOverlay = document.createElement('div');
  kernelOverlay.className = 'conv-kernel';
  inputGridEl.appendChild(kernelOverlay);

  // Kernel display (separate small grid showing kernel values)
  const kernelWrap = document.createElement('div');
  kernelWrap.style.cssText = 'display:flex; flex-direction:column; align-items:center; gap:6px;';
  const kernelLabel = document.createElement('div');
  kernelLabel.className = 'label accent-yellow';
  kernelLabel.textContent = 'Kernel (3×3)';
  kernelWrap.appendChild(kernelLabel);

  const kernelGridEl = document.createElement('div');
  kernelGridEl.className = 'conv-grid';
  kernelGridEl.style.cssText = `grid-template-columns:repeat(${{kernelSize}},1fr);`;
  const kernelData = [[1,0,1],[0,1,0],[1,0,1]];
  for (let r = 0; r < kernelSize; r++) {{
    for (let c = 0; c < kernelSize; c++) {{
      const cell = document.createElement('div');
      cell.className = 'conv-cell';
      cell.style.borderColor = '#d29922';
      cell.textContent = kernelData[r][c];
      kernelGridEl.appendChild(cell);
    }}
  }}
  kernelWrap.appendChild(kernelGridEl);
  convLayout.appendChild(kernelWrap);

  // Arrow between kernel and output
  const arrowEl = document.createElement('div');
  arrowEl.className = 'label';
  arrowEl.textContent = '→';
  arrowEl.style.fontSize = '1.5rem';
  convLayout.appendChild(arrowEl);

  // Output grid (3x3 for stride=1, no padding)
  const outputSize = inputSize - kernelSize + 1;
  const outputWrap = document.createElement('div');
  outputWrap.style.cssText = 'display:flex; flex-direction:column; align-items:center; gap:6px;';
  const outputLabel = document.createElement('div');
  outputLabel.className = 'label accent-green';
  outputLabel.textContent = `Output (${{outputSize}}×${{outputSize}})`;
  outputWrap.appendChild(outputLabel);

  const outputGridEl = document.createElement('div');
  outputGridEl.className = 'conv-grid';
  outputGridEl.style.cssText = `grid-template-columns:repeat(${{outputSize}},1fr);`;
  const outputCells = [];
  for (let r = 0; r < outputSize; r++) {{
    outputCells[r] = [];
    for (let c = 0; c < outputSize; c++) {{
      const cell = document.createElement('div');
      cell.className = 'conv-cell';
      cell.textContent = '—';
      outputGridEl.appendChild(cell);
      outputCells[r][c] = cell;
    }}
  }}
  outputWrap.appendChild(outputGridEl);
  convLayout.appendChild(outputWrap);

  gsap.set(convLayout, {{opacity:0}});

  // Animate kernel sliding across input:
  // For each position (r,c), move kernel overlay, highlight input cells, compute output
  function animateConvStep(r, c, value, label) {{
    const cellSize = inputCells[0][0].getBoundingClientRect();
    // Position kernel overlay (approximate with %)
    tl.to(kernelOverlay, {{
      left: c * cellSize.width + 'px',
      top: r * cellSize.height + 'px',
      width: kernelSize * cellSize.width + 'px',
      height: kernelSize * cellSize.height + 'px',
      duration: 0.4, ease:'power2.out'
    }}, label);
    // Highlight input cells under kernel
    for (let kr = 0; kr < kernelSize; kr++) {{
      for (let kc = 0; kc < kernelSize; kc++) {{
        tl.to(inputCells[r+kr][c+kc], {{borderColor:'#d29922', duration:0.2}}, label);
      }}
    }}
    // Fill output cell
    tl.call(() => {{ outputCells[r][c].textContent = value; }}, null, label + '+=0.5');
    tl.to(outputCells[r][c], {{borderColor:'#3fb950', color:'#3fb950', duration:0.3}}, label + '+=0.5');
    // Reset input highlights
    tl.call(() => {{
      for (let kr = 0; kr < kernelSize; kr++)
        for (let kc = 0; kc < kernelSize; kc++)
          inputCells[r+kr][c+kc].style.borderColor = '#30363d';
    }}, null, label + '+=0.9');
  }}"""
