"""Recipe: Stack & Queue — LIFO/FIFO containers, push/pop, enqueue/dequeue, call stacks."""

ID = "stack_queue"

KEYWORDS = [
    "stack", "queue", "push", "pop", "enqueue", "dequeue", "fifo", "lifo",
    "call stack", "function call", "recursion", "undo", "redo",
    "priority queue", "deque", "circular queue", "bfs queue",
    "dfs stack", "backtracking", "depth first",
]

CSS_DOCS = """\
STACK / QUEUE COMPONENTS:
  .stack-container — vertical flex container (column-reverse, items stack up)
  .queue-container — horizontal flex container (items flow left to right)
  .stack-item      — styled item in stack (dark bg, monospace)
  .queue-item      — styled item in queue (dark bg, monospace)
  .stack-item.hl, .queue-item.hl — blue highlight (top/front item)
  .stack-item.active, .queue-item.active — yellow highlight (being processed)"""

PATTERN = """\
STACK (vertical LIFO container — items enter and leave from top):
  const stackWrap = document.createElement('div');
  stackWrap.style.cssText = 'display:flex; flex-direction:column; align-items:center; gap:8px;';

  const stackLabel = document.createElement('div');
  stackLabel.className = 'label';
  stackLabel.textContent = 'Stack';
  stackWrap.appendChild(stackLabel);

  const stackEl = document.createElement('div');
  stackEl.className = 'stack-container';
  stackWrap.appendChild(stackEl);
  mainZone.appendChild(stackWrap);

  // Push item onto stack:
  function pushItem(value) {{
    const item = document.createElement('div');
    item.className = 'stack-item';
    item.textContent = value;
    gsap.set(item, {{opacity:0, y:-20}});
    stackEl.appendChild(item);
    return item;
  }}

  const item1 = pushItem('A');
  tl.to(item1, {{opacity:1, y:0, duration:0.4}}, 'push-A');

  // Pop (top item slides out):
  tl.to(item1, {{opacity:0, y:-30, duration:0.4}}, 'pop');
  tl.call(() => {{ item1.remove(); }}, null, 'pop+=0.5');

  // Highlight top of stack:
  tl.call(() => {{ stackEl.lastElementChild?.classList.add('hl'); }}, null, 'peek');

QUEUE (horizontal FIFO container — items enter right, leave left):
  const queueEl = document.createElement('div');
  queueEl.className = 'queue-container';
  mainZone.appendChild(queueEl);

  function enqueueItem(value) {{
    const item = document.createElement('div');
    item.className = 'queue-item';
    item.textContent = value;
    gsap.set(item, {{opacity:0, x:30}});
    queueEl.appendChild(item);
    return item;
  }}

  // Enqueue (slides in from right):
  const q1 = enqueueItem('X');
  tl.to(q1, {{opacity:1, x:0, duration:0.4}}, 'enqueue');

  // Dequeue (front item slides out left):
  tl.to(queueEl.firstElementChild, {{opacity:0, x:-30, duration:0.4}}, 'dequeue');

CALL STACK (function frames stacking up during recursion):
  // Each frame is a card showing function name + local variables
  function makeFrame(name, vars) {{
    const frame = document.createElement('div');
    frame.className = 'card';
    frame.style.cssText = 'padding:8px 14px; min-width:200px;';
    frame.innerHTML = `<div class="mono accent-blue" style="font-size:0.8rem;">${{name}}</div>` +
      Object.entries(vars).map(([k,v]) => `<div class="mono" style="font-size:0.7rem; color:#8b949e;">${{k}} = ${{v}}</div>`).join('');
    return frame;
  }}"""
