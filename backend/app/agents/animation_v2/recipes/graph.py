"""Recipe: Graph — general graphs, adjacency, traversal, shortest path, MST."""

ID = "graph"

KEYWORDS = [
    "graph traversal", "vertex", "vertices", "edge weight", "edges",
    "adjacency list", "adjacency matrix", "directed graph", "undirected graph",
    "dijkstra", "bellman", "ford", "prim", "kruskal", "mst",
    "spanning tree", "topological sort", "strongly connected", "cycle detection",
    "shortest path", "bfs traversal", "dfs traversal", "a star", "a*",
    "heuristic search", "graph node", "network flow", "bipartite", "graph coloring",
]

CSS_DOCS = """\
GRAPH COMPONENTS:
  .graph-node    — circular node (absolute positioned, dark bg, monospace)
  .graph-node.visited — green border (visited in traversal)
  .graph-node.current — yellow glow (currently processing)
  .graph-node.queued  — purple border (in queue/frontier)
  .graph-weight  — small label for edge weights (absolute, dark bg behind text)
  Use SVG lines/paths for edges. Use marker-end for directed arrows."""

PATTERN = """\
GRAPH (nodes + edges, traversal, shortest path, MST):
  // Container with SVG for edges and absolute-positioned node divs
  const graphContainer = document.createElement('div');
  graphContainer.style.cssText = 'position:relative; width:100%; height:100%;';
  mainZone.appendChild(graphContainer);

  // SVG edge layer
  const svgNs = 'http://www.w3.org/2000/svg';
  const edgeSvg = document.createElementNS(svgNs, 'svg');
  edgeSvg.style.cssText = 'position:absolute; top:0; left:0; width:100%; height:100%; pointer-events:none;';
  // Arrow marker for directed graphs
  const defs = document.createElementNS(svgNs, 'defs');
  const marker = document.createElementNS(svgNs, 'marker');
  marker.setAttribute('id', 'arrowhead');
  marker.setAttribute('markerWidth', '10');
  marker.setAttribute('markerHeight', '7');
  marker.setAttribute('refX', '10');
  marker.setAttribute('refY', '3.5');
  marker.setAttribute('orient', 'auto');
  const arrowPath = document.createElementNS(svgNs, 'polygon');
  arrowPath.setAttribute('points', '0 0, 10 3.5, 0 7');
  arrowPath.setAttribute('fill', '#30363d');
  marker.appendChild(arrowPath);
  defs.appendChild(marker);
  edgeSvg.appendChild(defs);
  graphContainer.appendChild(edgeSvg);

  // Node positions (% based for responsiveness)
  const nodeData = [
    {{ id:'A', x:20, y:30 }}, {{ id:'B', x:50, y:15 }},
    {{ id:'C', x:80, y:30 }}, {{ id:'D', x:35, y:65 }},
    {{ id:'E', x:65, y:65 }},
  ];
  const edgeData = [
    {{ from:'A', to:'B', weight:4 }}, {{ from:'B', to:'C', weight:2 }},
    {{ from:'A', to:'D', weight:6 }}, {{ from:'D', to:'E', weight:3 }},
    {{ from:'B', to:'E', weight:5 }}, {{ from:'C', to:'E', weight:1 }},
  ];

  // Create nodes
  const nodes = {{}};
  nodeData.forEach(n => {{
    const el = document.createElement('div');
    el.className = 'graph-node';
    el.textContent = n.id;
    el.style.cssText = `left:${{n.x}}%; top:${{n.y}}%; transform:translate(-50%,-50%);`;
    graphContainer.appendChild(el);
    nodes[n.id] = {{ el, x:n.x, y:n.y }};
  }});

  // Create edges
  const edgeEls = edgeData.map(e => {{
    const line = document.createElementNS(svgNs, 'line');
    line.setAttribute('x1', nodes[e.from].x + '%');
    line.setAttribute('y1', nodes[e.from].y + '%');
    line.setAttribute('x2', nodes[e.to].x + '%');
    line.setAttribute('y2', nodes[e.to].y + '%');
    line.setAttribute('stroke', '#30363d');
    line.setAttribute('stroke-width', '2');
    line.setAttribute('marker-end', 'url(#arrowhead)');  // for directed
    line.setAttribute('opacity', '0');
    edgeSvg.appendChild(line);
    // Weight label
    if (e.weight !== undefined) {{
      const wLabel = document.createElement('div');
      wLabel.className = 'graph-weight';
      wLabel.textContent = e.weight;
      const mx = (nodes[e.from].x + nodes[e.to].x) / 2;
      const my = (nodes[e.from].y + nodes[e.to].y) / 2;
      wLabel.style.cssText = `left:${{mx}}%; top:${{my}}%; transform:translate(-50%,-50%);`;
      graphContainer.appendChild(wLabel);
      gsap.set(wLabel, {{opacity:0}});
    }}
    return line;
  }});

  gsap.set(Object.values(nodes).map(n => n.el), {{opacity:0, scale:0.5}});

  // Reveal graph:
  tl.to(Object.values(nodes).map(n => n.el), {{opacity:1, scale:1, duration:0.4, stagger:0.1}}, 'show-graph');
  tl.to(edgeEls, {{opacity:1, duration:0.3, stagger:0.08}}, 'show-graph+=1');

  // BFS/DFS traversal: mark current → visited
  tl.to(nodes['A'].el, {{borderColor:'#d29922', boxShadow:'0 0 12px rgba(210,153,34,0.4)', duration:0.4}}, 'visit-A');
  tl.to(nodes['A'].el, {{borderColor:'#3fb950', color:'#3fb950', boxShadow:'none', duration:0.3}}, 'visit-A+=1');

  // Highlight edge (e.g. shortest path):
  tl.to(_t(line), {{attr:{{stroke:'#58a6ff', 'stroke-width':'3'}}, duration:0.4}}, 'path');"""
