"""Recipe: Code — syntax-highlighted blocks, line-by-line reveal, variable tracking."""

ID = "code"

KEYWORDS = [
    "code block", "source code", "syntax highlight", "code walkthrough",
    "line by line", "step through", "debug", "variable tracker", "trace",
    "algorithm implementation", "pseudocode", "python code",
    "javascript code", "java code", "c++ code", "code snippet", "execution",
    "runtime", "compile", "print statement", "return value",
]

CSS_DOCS = """\
CODE COMPONENTS:
  .code-box      — dark code block (monospace, rounded, padded)
  .code-line     — single line of code (white-space:pre)
  .code-line.hl  — highlighted line (blue left border + blue bg tint)
  Prism.js is pre-loaded for syntax highlighting (prism-python, etc.)"""

PATTERN = """\
CODE BLOCK (syntax-highlighted code with line-by-line walkthrough):
  const codeBox = document.createElement('div');
  codeBox.className = 'code-box';
  codeBox.style.cssText = 'max-width:700px; width:90%;';

  const codeLines = [
    'def binary_search(arr, target):',
    '    low, high = 0, len(arr) - 1',
    '    while low <= high:',
    '        mid = (low + high) // 2',
    '        if arr[mid] == target:',
    '            return mid',
    '        elif arr[mid] < target:',
    '            low = mid + 1',
    '        else:',
    '            high = mid - 1',
    '    return -1',
  ];
  const lineEls = codeLines.map(line => {{
    const el = document.createElement('div');
    el.className = 'code-line';
    el.textContent = line;
    codeBox.appendChild(el);
    return el;
  }});
  mainZone.appendChild(codeBox);
  gsap.set(codeBox, {{opacity:0}});

  // Reveal entire block:
  tl.to(codeBox, {{opacity:1, duration:0.8}}, 'show-code');

  // Highlight current line (move highlight through execution):
  function highlightLine(idx, label) {{
    // Remove previous highlights
    tl.call(() => {{
      lineEls.forEach(el => el.classList.remove('hl'));
      lineEls[idx].classList.add('hl');
    }}, null, label);
    tl.to(lineEls[idx], {{backgroundColor:'rgba(56,139,253,0.1)', duration:0.3}}, label);
  }}
  highlightLine(0, 'exec-line-1');
  highlightLine(1, 'exec-line-2');

  // Prism.js syntax highlighting (apply after creating elements):
  // Use Prism.highlight() for colored tokens:
  const highlighted = Prism.highlight(codeLines.join('\\n'), Prism.languages.python, 'python');
  // Or apply per-line for walkthrough control

VARIABLE TRACKER (side panel showing variable state changes):
  const varPanel = document.createElement('div');
  varPanel.className = 'card';
  varPanel.style.cssText = 'position:absolute; right:2%; top:20%; width:180px; padding:12px;';
  c.appendChild(varPanel);

  const varTitle = document.createElement('div');
  varTitle.className = 'label accent-blue';
  varTitle.textContent = 'Variables';
  varTitle.style.marginBottom = '8px';
  varPanel.appendChild(varTitle);

  function makeVarRow(name, value) {{
    const row = document.createElement('div');
    row.style.cssText = 'display:flex; justify-content:space-between; padding:3px 0;';
    row.innerHTML = `<span class="mono" style="color:#8b949e; font-size:0.75rem;">${{name}}</span>` +
                    `<span class="mono accent-green" style="font-size:0.75rem;">${{value}}</span>`;
    varPanel.appendChild(row);
    return row;
  }}

  const lowVar = makeVarRow('low', '0');
  const highVar = makeVarRow('high', '9');
  gsap.set(varPanel, {{opacity:0}});

  // Update variable value:
  tl.call(() => {{ lowVar.querySelector('.accent-green').textContent = '5'; }}, null, 'update-vars');
  tl.to(lowVar, {{backgroundColor:'rgba(210,153,34,0.15)', duration:0.3}}, 'update-vars');
  tl.to(lowVar, {{backgroundColor:'transparent', duration:0.3}}, 'update-vars+=0.8');

OUTPUT PANEL (showing program output):
  const outputBox = document.createElement('div');
  outputBox.className = 'code-box';
  outputBox.style.cssText = 'max-width:400px; border-color:#3fb950; margin-top:10px;';
  const outputLabel = document.createElement('div');
  outputLabel.className = 'label accent-green';
  outputLabel.textContent = 'Output';
  outputLabel.style.marginBottom = '4px';
  outputBox.appendChild(outputLabel);
  mainZone.appendChild(outputBox);

  // Append output lines over time:
  tl.call(() => {{
    const line = document.createElement('div');
    line.className = 'code-line';
    line.textContent = '>>> Found at index 5';
    line.style.color = '#3fb950';
    outputBox.appendChild(line);
  }}, null, 'output');"""
