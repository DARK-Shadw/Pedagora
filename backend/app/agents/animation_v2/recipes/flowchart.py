"""Recipe: Flowchart — process diagrams, decision flows, data pipelines, architecture."""

ID = "flowchart"

KEYWORDS = [
    "flowchart", "flow chart", "process", "pipeline", "data flow",
    "architecture", "diagram", "workflow", "state machine", "state diagram",
    "decision", "branch", "if else", "condition", "step by step",
    "sequential", "parallel", "fork", "join", "etl", "data pipeline",
    "input output", "block diagram", "system design", "microservice",
    "layer", "forward pass", "backward pass",
]

CSS_DOCS = """\
FLOWCHART COMPONENTS:
  .flow-box       — process box (rounded, dark bg, absolute positioned)
  .flow-box.start, .flow-box.end — pill-shaped start/end boxes
  .flow-diamond   — decision diamond (rotated 45°, yellow border)
  .flow-diamond span — text inside diamond (counter-rotated)
  .flow-box.hl    — blue glow highlight (currently active step)
  Use SVG lines with marker-end='url(#arrowhead)' for connectors."""

PATTERN = """\
FLOWCHART (process boxes, decision diamonds, SVG arrow connectors):
  // Container for absolute positioning
  const flowContainer = document.createElement('div');
  flowContainer.style.cssText = 'position:relative; width:100%; height:100%;';
  mainZone.appendChild(flowContainer);

  // SVG layer for arrows
  const svgNs = 'http://www.w3.org/2000/svg';
  const arrowSvg = document.createElementNS(svgNs, 'svg');
  arrowSvg.style.cssText = 'position:absolute; top:0; left:0; width:100%; height:100%; pointer-events:none;';
  const defs = document.createElementNS(svgNs, 'defs');
  const marker = document.createElementNS(svgNs, 'marker');
  marker.setAttribute('id', 'flowArrow');
  marker.setAttribute('markerWidth', '10');
  marker.setAttribute('markerHeight', '7');
  marker.setAttribute('refX', '10');
  marker.setAttribute('refY', '3.5');
  marker.setAttribute('orient', 'auto');
  const poly = document.createElementNS(svgNs, 'polygon');
  poly.setAttribute('points', '0 0, 10 3.5, 0 7');
  poly.setAttribute('fill', '#58a6ff');
  marker.appendChild(poly);
  defs.appendChild(marker);
  arrowSvg.appendChild(defs);
  flowContainer.appendChild(arrowSvg);

  // Process boxes (positioned with %)
  function makeFlowBox(text, x, y, type='') {{
    const box = document.createElement('div');
    box.className = 'flow-box' + (type ? ' ' + type : '');
    box.textContent = text;
    box.style.cssText = `left:${{x}}%; top:${{y}}%; transform:translate(-50%,-50%);`;
    flowContainer.appendChild(box);
    return box;
  }}

  // Decision diamond
  function makeDiamond(text, x, y) {{
    const diamond = document.createElement('div');
    diamond.className = 'flow-diamond';
    diamond.innerHTML = `<span>${{text}}</span>`;
    diamond.style.cssText = `left:${{x}}%; top:${{y}}%; transform:translate(-50%,-50%) rotate(45deg);`;
    flowContainer.appendChild(diamond);
    return diamond;
  }}

  // Arrow connector (SVG line between two % positions)
  function makeArrow(x1, y1, x2, y2) {{
    const line = document.createElementNS(svgNs, 'line');
    line.setAttribute('x1', x1+'%'); line.setAttribute('y1', y1+'%');
    line.setAttribute('x2', x2+'%'); line.setAttribute('y2', y2+'%');
    line.setAttribute('stroke', '#58a6ff'); line.setAttribute('stroke-width', '2');
    line.setAttribute('marker-end', 'url(#flowArrow)'); line.setAttribute('opacity', '0');
    arrowSvg.appendChild(line);
    return line;
  }}

  // Example: Input → Process → Decision → Output
  const start = makeFlowBox('Input Data', 50, 10, 'start');
  const proc1 = makeFlowBox('Preprocess', 50, 30);
  const decide = makeDiamond('Valid?', 50, 55);
  const proc2 = makeFlowBox('Train Model', 50, 80);
  const reject = makeFlowBox('Error', 80, 55);

  const a1 = makeArrow(50, 16, 50, 24);
  const a2 = makeArrow(50, 36, 50, 44);
  const a3 = makeArrow(50, 66, 50, 74);
  const a4 = makeArrow(60, 55, 72, 55);  // decision → reject branch

  gsap.set([start, proc1, decide, proc2, reject], {{opacity:0, y:10}});

  // Reveal top-down:
  tl.to(start, {{opacity:1, y:0, duration:0.5}}, 'show-flow');
  tl.to(_t(a1), {{opacity:1, duration:0.3}}, 'show-flow+=0.5');
  tl.to(proc1, {{opacity:1, y:0, duration:0.5}}, 'show-flow+=0.8');

  // Highlight active step:
  tl.to(proc1, {{borderColor:'#388bfd', boxShadow:'0 0 12px rgba(56,139,253,0.3)', duration:0.4}}, 'active-step');"""
