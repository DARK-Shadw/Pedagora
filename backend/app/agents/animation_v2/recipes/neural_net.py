"""Recipe: Neural Network — layers, neurons, connections, forward/backward pass."""

ID = "neural_net"

KEYWORDS = [
    "neural network", "neuron", "layer diagram", "perceptron", "mlp",
    "multi-layer", "hidden layer", "input layer", "output layer",
    "network architecture", "bias node", "activation function",
    "forward pass", "backpropagation", "backward pass",
    "deep learning architecture", "deep neural", "feedforward",
    "fully connected", "dense layer",
    "autoencoder", "gan architecture", "generative adversarial",
    "discriminator network", "encoder decoder",
]

CSS_DOCS = """\
NEURAL NETWORK COMPONENTS:
  .nn-neuron       — small circle node (absolute positioned)
  .nn-neuron.active — blue glow (receiving activation)
  .nn-neuron.fired  — green (activated/output)
  .nn-neuron.input  — yellow border (input layer)
  .nn-neuron.output — purple border (output layer)
  .nn-label        — small label for layer names
  Use SVG lines for connections between neurons."""

PATTERN = """\
NEURAL NETWORK (layers of neurons with weighted connections):
  // Container with SVG for connections and divs for neurons
  const nnContainer = document.createElement('div');
  nnContainer.style.cssText = 'position:relative; width:100%; height:100%;';
  mainZone.appendChild(nnContainer);

  // SVG for connection lines
  const svgNs = 'http://www.w3.org/2000/svg';
  const connSvg = document.createElementNS(svgNs, 'svg');
  connSvg.style.cssText = 'position:absolute; top:0; left:0; width:100%; height:100%; pointer-events:none;';
  nnContainer.appendChild(connSvg);

  // Layer configuration: [inputSize, hidden1, hidden2, ..., outputSize]
  const layers = [3, 5, 4, 2];
  const layerLabels = ['Input', 'Hidden 1', 'Hidden 2', 'Output'];
  const neuronEls = [];  // neuronEls[layer][neuron]
  const connEls = [];    // flat array of all connection SVG lines

  // Position neurons in columns
  const layerSpacing = 80 / (layers.length - 1);  // % horizontal spread
  layers.forEach((size, li) => {{
    neuronEls[li] = [];
    const x = 10 + li * layerSpacing;  // 10%–90% horizontal
    const neuronSpacing = Math.min(15, 70 / size);
    const startY = 50 - (size - 1) * neuronSpacing / 2;

    for (let ni = 0; ni < size; ni++) {{
      const y = startY + ni * neuronSpacing;
      const neuron = document.createElement('div');
      neuron.className = 'nn-neuron';
      if (li === 0) neuron.classList.add('input');
      if (li === layers.length - 1) neuron.classList.add('output');
      neuron.style.cssText = `left:${{x}}%; top:${{y}}%; transform:translate(-50%,-50%);`;
      nnContainer.appendChild(neuron);
      neuronEls[li][ni] = {{ el: neuron, x, y }};
    }}

    // Layer label below neurons
    const label = document.createElement('div');
    label.className = 'nn-label';
    label.textContent = layerLabels[li] || `Layer ${{li}}`;
    label.style.cssText = `position:absolute; left:${{x}}%; bottom:5%; transform:translateX(-50%);`;
    nnContainer.appendChild(label);

    // Connections to previous layer
    if (li > 0) {{
      neuronEls[li - 1].forEach(prev => {{
        neuronEls[li].forEach(curr => {{
          const line = document.createElementNS(svgNs, 'line');
          line.setAttribute('x1', prev.x + '%');
          line.setAttribute('y1', prev.y + '%');
          line.setAttribute('x2', curr.x + '%');
          line.setAttribute('y2', curr.y + '%');
          line.setAttribute('stroke', '#30363d');
          line.setAttribute('stroke-width', '1');
          line.setAttribute('opacity', '0');
          connSvg.appendChild(line);
          connEls.push(line);
        }});
      }});
    }}
  }});

  // Hide all neurons
  const allNeurons = neuronEls.flat().map(n => n.el);
  gsap.set(allNeurons, {{opacity:0, scale:0.5}});

  // Reveal layer by layer:
  layers.forEach((_, li) => {{
    const layerNeurons = neuronEls[li].map(n => n.el);
    tl.to(layerNeurons, {{opacity:1, scale:1, duration:0.4, stagger:0.05}}, `show-layer-${{li}}`);
  }});
  // Show connections after all layers visible:
  tl.to(connEls.map(l => _t(l)), {{opacity:0.4, duration:0.5}}, 'show-connections');

  // FORWARD PASS animation (activation flows left to right):
  // Light up input neurons, then connections pulse, then hidden neurons, etc.
  function animateForwardLayer(fromLayer, toLayer, label) {{
    // Pulse connections from fromLayer to toLayer
    const layerConns = [];
    const startIdx = layers.slice(0, fromLayer).reduce((sum, s, i) =>
      sum + s * layers[i + 1], 0);
    const count = layers[fromLayer] * layers[toLayer];
    for (let i = startIdx; i < startIdx + count; i++) {{
      if (connEls[i]) layerConns.push(connEls[i]);
    }}
    tl.to(layerConns.map(l => _t(l)), {{
      attr: {{stroke: '#58a6ff', 'stroke-width': '2'}},
      opacity: 0.8, duration: 0.5
    }}, label);
    // Light up target neurons
    tl.to(neuronEls[toLayer].map(n => n.el), {{
      borderColor: '#58a6ff', boxShadow: '0 0 10px rgba(56,139,253,0.3)',
      duration: 0.4, stagger: 0.05
    }}, label + '+=0.3');
    // Reset connections
    tl.to(layerConns.map(l => _t(l)), {{
      attr: {{stroke: '#30363d', 'stroke-width': '1'}},
      opacity: 0.4, duration: 0.3
    }}, label + '+=1');
  }}

  // BACKPROPAGATION (reverse direction, red color):
  // Same pattern but right-to-left with #f85149 color"""
