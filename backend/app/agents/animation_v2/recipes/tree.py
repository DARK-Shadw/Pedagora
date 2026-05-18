"""Recipe: Tree — binary trees, BSTs, AVL, heaps, tries, game trees, decision trees."""

ID = "tree"

KEYWORDS = [
    "tree", "binary tree", "bst", "binary search tree", "avl", "red-black",
    "heap", "min heap", "max heap", "trie", "prefix tree", "b-tree",
    "decision tree", "game tree", "minimax", "alpha beta", "parse tree",
    "traversal", "inorder", "preorder", "postorder", "level order",
    "bfs", "dfs", "insert", "delete", "rotate", "balance", "huffman",
    "segment tree", "fenwick", "parent", "child", "leaf", "root",
]

CSS_DOCS = """\
TREE COMPONENTS:
  .tree-node     — circular node (absolute positioned, dark bg, monospace)
  .tree-node.hl  — blue glow highlight (current node in traversal)
  Use SVG lines for edges between nodes. Position nodes with absolute top/left."""

PATTERN = """\
TREE (binary trees, BSTs, heaps, game trees, decision trees):
  // Use SVG for edges, absolute-positioned divs for nodes
  const treeContainer = document.createElement('div');
  treeContainer.style.cssText = 'position:relative; width:100%; height:100%;';
  mainZone.appendChild(treeContainer);

  // SVG layer for edges (behind nodes)
  const svgNs = 'http://www.w3.org/2000/svg';
  const edgeSvg = document.createElementNS(svgNs, 'svg');
  edgeSvg.style.cssText = 'position:absolute; top:0; left:0; width:100%; height:100%; pointer-events:none;';
  treeContainer.appendChild(edgeSvg);

  // Layout helper: compute x,y for each node in a binary tree
  // Root at (50%, 8%), each level +18% down, spread halves per level
  function layoutTree(nodes) {{
    // nodes = [{{value, left, right}}] — breadth-first array (null for empty)
    const positions = [];
    const levels = Math.ceil(Math.log2(nodes.length + 1));
    for (let i = 0; i < nodes.length; i++) {{
      if (!nodes[i]) continue;
      const level = Math.floor(Math.log2(i + 1));
      const posInLevel = i - (Math.pow(2, level) - 1);
      const totalInLevel = Math.pow(2, level);
      const xPct = ((posInLevel + 0.5) / totalInLevel) * 80 + 10; // 10%-90% range
      const yPct = 8 + level * (70 / levels);  // spread across 8%-78%
      positions[i] = {{ x: xPct, y: yPct, value: nodes[i] }};
    }}
    return positions;
  }}

  // Create nodes
  const treeData = [50, 30, 70, 20, 40, 60, 80]; // breadth-first
  const pos = layoutTree(treeData);
  const treeNodes = [];
  pos.forEach((p, i) => {{
    if (!p) return;
    const node = document.createElement('div');
    node.className = 'tree-node';
    node.textContent = p.value;
    node.style.cssText = `left:${{p.x}}%; top:${{p.y}}%; transform:translate(-50%,-50%);`;
    treeContainer.appendChild(node);
    treeNodes[i] = node;
  }});

  // Create edges (parent i → children 2i+1, 2i+2)
  const edges = [];
  pos.forEach((p, i) => {{
    if (!p) return;
    [2*i+1, 2*i+2].forEach(childIdx => {{
      if (!pos[childIdx]) return;
      const line = document.createElementNS(svgNs, 'line');
      line.setAttribute('x1', p.x + '%');
      line.setAttribute('y1', p.y + '%');
      line.setAttribute('x2', pos[childIdx].x + '%');
      line.setAttribute('y2', pos[childIdx].y + '%');
      line.setAttribute('stroke', '#30363d');
      line.setAttribute('stroke-width', '2');
      line.setAttribute('opacity', '0');
      edgeSvg.appendChild(line);
      edges.push(line);
    }});
  }});

  // Hide everything, then reveal
  gsap.set(treeNodes.filter(Boolean), {{opacity:0, scale:0.5}});

  // Reveal tree level by level:
  tl.to(treeNodes[0], {{opacity:1, scale:1, duration:0.5}}, 'show-tree');
  tl.to(edges.slice(0,2), {{opacity:1, duration:0.3, stagger:0.1}}, 'show-tree+=0.5');
  tl.to([treeNodes[1], treeNodes[2]], {{opacity:1, scale:1, duration:0.4, stagger:0.15}}, 'show-tree+=0.8');

  // Traversal highlight (node turns blue, then green for "visited"):
  tl.to(treeNodes[i], {{borderColor:'#d29922', boxShadow:'0 0 12px rgba(210,153,34,0.4)', duration:0.4}}, 'visit');
  tl.to(treeNodes[i], {{borderColor:'#3fb950', color:'#3fb950', boxShadow:'none', duration:0.3}}, 'visit+=1');

  // AVL rotation: fade out subtree, rearrange positions, fade in
  tl.to([nodeA, nodeB], {{opacity:0, duration:0.3}}, 'rotate');
  tl.call(() => {{
    nodeA.style.left = newPosA.x + '%'; nodeA.style.top = newPosA.y + '%';
    nodeB.style.left = newPosB.x + '%'; nodeB.style.top = newPosB.y + '%';
  }}, null, 'rotate+=0.4');
  tl.to([nodeA, nodeB], {{opacity:1, duration:0.3}}, 'rotate+=0.5');"""
