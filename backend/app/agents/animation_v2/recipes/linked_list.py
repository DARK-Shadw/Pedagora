"""Recipe: Linked List — singly/doubly linked lists, insertion, deletion, reversal."""

ID = "linked_list"

KEYWORDS = [
    "linked list", "singly linked", "doubly linked", "linkedlist",
    "next pointer", "prev pointer", "head node", "tail node",
    "insert node", "delete node", "reverse list",
    "cycle detection", "fast slow pointer", "tortoise hare",
    "merge lists", "sentinel node", "dummy node",
]

CSS_DOCS = """\
LINKED LIST COMPONENTS:
  .ll-node       — inline-flex node with data + next sections
  .ll-node .ll-data  — left section (value)
  .ll-node .ll-next  — right section (pointer indicator)
  .ll-node.hl    — blue glow highlight
  .ll-node.found — green highlight
  .ll-arrow      — arrow between nodes (→ character or CSS arrow)
  .ll-null       — "null" terminator label"""

PATTERN = """\
LINKED LIST (node chains with pointers, insert/delete/reverse):
  // Horizontal chain of nodes with arrows
  const llContainer = document.createElement('div');
  llContainer.style.cssText = 'display:flex; align-items:center; gap:4px; flex-wrap:wrap; justify-content:center;';
  mainZone.appendChild(llContainer);

  function makeLLNode(value) {{
    const node = document.createElement('div');
    node.className = 'll-node';
    node.innerHTML = `<span class="ll-data">${{value}}</span><span class="ll-next">•</span>`;
    return node;
  }}
  function makeLLArrow() {{
    const arrow = document.createElement('span');
    arrow.className = 'll-arrow';
    arrow.textContent = '→';
    return arrow;
  }}

  const values = [3, 7, 12, 18, 22];
  const llNodes = [];
  const llArrows = [];
  values.forEach((v, i) => {{
    const node = makeLLNode(v);
    llContainer.appendChild(node);
    llNodes.push(node);
    if (i < values.length - 1) {{
      const arrow = makeLLArrow();
      llContainer.appendChild(arrow);
      llArrows.push(arrow);
    }}
  }});
  // Null terminator
  const nullEl = document.createElement('span');
  nullEl.className = 'll-null';
  nullEl.textContent = 'null';
  llContainer.appendChild(nullEl);

  // Head pointer label
  const headLabel = document.createElement('div');
  headLabel.className = 'label mono accent-blue';
  headLabel.textContent = 'head';
  headLabel.style.cssText = 'position:absolute; top:-20px;';

  gsap.set(llNodes, {{opacity:0, x:-20}});
  gsap.set(llArrows, {{opacity:0}});

  // Reveal list node by node:
  tl.to(llNodes, {{opacity:1, x:0, duration:0.4, stagger:0.15}}, 'show-list');
  tl.to(llArrows, {{opacity:1, duration:0.2, stagger:0.15}}, 'show-list+=0.2');

  // Insert new node (fade in between existing nodes):
  const newNode = makeLLNode(15);
  const newArrow = makeLLArrow();
  gsap.set([newNode, newArrow], {{opacity:0, y:-20}});
  // Insert into DOM at correct position
  llContainer.insertBefore(newArrow, llNodes[2]);
  llContainer.insertBefore(newNode, newArrow);
  tl.to([newNode, newArrow], {{opacity:1, y:0, duration:0.5}}, 'insert');

  // Delete node (fade out node + its arrow, close gap):
  tl.to([llNodes[2], llArrows[2]], {{opacity:0, y:20, duration:0.4}}, 'delete');
  tl.call(() => {{ llNodes[2].remove(); llArrows[2].remove(); }}, null, 'delete+=0.5');

  // Highlight traversal:
  tl.to(llNodes[i], {{borderColor:'#d29922', boxShadow:'0 0 10px rgba(210,153,34,0.3)', duration:0.3}}, 'traverse');"""
