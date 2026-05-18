"""Recipe: Coordinate plane — D3 axes, function plots, scatter, decision boundaries."""

ID = "coordinate"

KEYWORDS = [
    "plot", "graph", "chart", "axis", "axes", "coordinate", "x-axis", "y-axis",
    "function", "curve", "parabola", "quadratic", "linear", "exponential",
    "logarithm", "sine", "cosine", "tangent", "derivative", "integral",
    "area under", "scatter", "scatter plot", "data point", "regression",
    "line of best fit", "decision boundary", "classification", "cluster",
    "loss curve", "training curve", "accuracy", "epoch", "convergence",
    "gradient descent", "contour", "histogram", "bar chart", "distribution",
    "knn", "k-nearest", "svm", "support vector",
]

CSS_DOCS = """\
COORDINATE / CHART COMPONENTS:
  D3.js is pre-loaded — use d3.select(), d3.scaleLinear(), etc.
  SVG elements are styled via attributes, not CSS classes.
  Standard colors: #58a6ff (primary line), #3fb950 (secondary), #d29922 (highlight)
  Axis text: fill '#8b949e', font-size 12px"""

PATTERN = """\
COORDINATE PLANE / CHART (D3.js axes, function plots, scatter, bar charts):
  // Create SVG inside mainZone
  const w = mainZone.clientWidth || 1100, h = mainZone.clientHeight || 450;
  const margin = {{top:30, right:40, bottom:50, left:60}};
  const innerW = w - margin.left - margin.right;
  const innerH = h - margin.top - margin.bottom;
  const svg = d3.select(mainZone).append('svg')
    .attr('width', w).attr('height', h)
    .attr('viewBox', `0 0 ${{w}} ${{h}}`);
  const g = svg.append('g').attr('transform', `translate(${{margin.left}},${{margin.top}})`);

  // Scales
  const xScale = d3.scaleLinear().domain([0, 10]).range([0, innerW]);
  const yScale = d3.scaleLinear().domain([0, 100]).range([innerH, 0]);

  // Axes (styled for dark theme)
  const xAxis = g.append('g')
    .attr('transform', `translate(0,${{innerH}})`)
    .call(d3.axisBottom(xScale).ticks(10));
  xAxis.selectAll('line,path').attr('stroke', '#30363d');
  xAxis.selectAll('text').attr('fill', '#8b949e').attr('font-size', '12px');

  const yAxis = g.append('g').call(d3.axisLeft(yScale).ticks(8));
  yAxis.selectAll('line,path').attr('stroke', '#30363d');
  yAxis.selectAll('text').attr('fill', '#8b949e').attr('font-size', '12px');

  // Axis labels
  g.append('text').attr('x', innerW/2).attr('y', innerH + 40)
    .attr('fill', '#8b949e').attr('text-anchor', 'middle').attr('font-size', '14px')
    .text('x');
  g.append('text').attr('x', -innerH/2).attr('y', -45)
    .attr('fill', '#8b949e').attr('text-anchor', 'middle').attr('font-size', '14px')
    .attr('transform', 'rotate(-90)').text('f(x)');

  gsap.set(svg.node(), {{opacity:0}});

  // FUNCTION PLOT (line graph):
  const lineData = d3.range(0, 10.1, 0.1).map(x => ({{ x, y: x*x }}));
  const line = d3.line()
    .x(d => xScale(d.x)).y(d => yScale(d.y));
  const path = g.append('path')
    .datum(lineData).attr('d', line)
    .attr('fill', 'none').attr('stroke', '#58a6ff').attr('stroke-width', 2.5);
  // Animate draw-on effect:
  const pathLen = path.node().getTotalLength();
  path.attr('stroke-dasharray', pathLen).attr('stroke-dashoffset', pathLen);
  tl.to(_t(path), {{strokeDashoffset:0, duration:2, ease:'none'}}, 'draw-curve');

  // SCATTER PLOT:
  const points = [{{x:2,y:15}}, {{x:4,y:35}}, {{x:6,y:55}}, {{x:8,y:80}}];
  const dots = points.map(p => {{
    return g.append('circle')
      .attr('cx', xScale(p.x)).attr('cy', yScale(p.y))
      .attr('r', 5).attr('fill', '#d29922').attr('opacity', 0);
  }});
  tl.to(dots.map(d => _t(d)), {{opacity:1, duration:0.3, stagger:0.15}}, 'show-points');

  // AREA UNDER CURVE (for integrals):
  const area = d3.area()
    .x(d => xScale(d.x)).y0(innerH).y1(d => yScale(d.y));
  const areaPath = g.append('path')
    .datum(lineData.filter(d => d.x >= 2 && d.x <= 6))
    .attr('d', area).attr('fill', 'rgba(63,185,80,0.2)')
    .attr('stroke', 'none').attr('opacity', 0);
  tl.to(_t(areaPath), {{opacity:1, duration:0.8}}, 'show-area');

  // DECISION BOUNDARY (classification):
  // Draw a line or curve separating two classes
  const boundaryLine = g.append('line')
    .attr('x1', xScale(0)).attr('y1', yScale(50))
    .attr('x2', xScale(10)).attr('y2', yScale(50))
    .attr('stroke', '#f85149').attr('stroke-width', 2)
    .attr('stroke-dasharray', '6,4').attr('opacity', 0);
  tl.to(_t(boundaryLine), {{opacity:1, duration:0.5}}, 'show-boundary');

  // BAR CHART:
  const barData = [{{label:'A', value:30}}, {{label:'B', value:65}}, {{label:'C', value:45}}];
  const barW = innerW / barData.length * 0.6;
  const bars = barData.map((d, i) => {{
    return g.append('rect')
      .attr('x', xScale(i * 3 + 1.5) - barW/2)
      .attr('y', yScale(d.value))
      .attr('width', barW)
      .attr('height', innerH - yScale(d.value))
      .attr('fill', '#58a6ff').attr('rx', 4).attr('opacity', 0);
  }});
  tl.to(bars.map(b => _t(b)), {{opacity:1, duration:0.4, stagger:0.15}}, 'show-bars');

  // GRID LINES (optional, subtle):
  const gridLines = g.append('g').attr('class', 'grid');
  yScale.ticks(8).forEach(tick => {{
    gridLines.append('line')
      .attr('x1', 0).attr('x2', innerW)
      .attr('y1', yScale(tick)).attr('y2', yScale(tick))
      .attr('stroke', '#21262d').attr('stroke-width', 0.5);
  }});"""
