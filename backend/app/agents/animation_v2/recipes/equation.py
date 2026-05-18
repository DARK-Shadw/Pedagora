"""Recipe: Equation — KaTeX formulas, step-by-step derivation, proof steps."""

ID = "equation"

KEYWORDS = [
    "equation", "formula", "derive", "derivation", "proof", "simplif",
    "expand", "factor", "integrate", "differentiat", "limit", "sum",
    "series", "converge", "diverge", "taylor", "fourier", "laplace",
    "eigenvalue", "determinant", "solve", "quadratic", "linear algebra",
    "calculus", "algebra", "trigonometr", "logarithm", "exponential",
    "probability", "bayes", "expected value", "variance", "distribution",
    "normal", "gaussian", "binomial", "poisson", "entropy", "cross entropy",
    "loss function", "gradient", "chain rule", "backpropagation formula",
    "softmax", "sigmoid", "relu", "activation function",
    "big o", "complexity", "recurrence", "master theorem",
]

CSS_DOCS = """\
EQUATION COMPONENTS:
  .zone-eq       — top 10%, full width centered (for standalone equations)
  .katex         — base KaTeX size (1.4em)
  .katex-lg      — large equation (1.8em)
  .katex-xl      — extra large equation (2.4em)
  .card          — dark card for derivation steps
  .card-accent   — card with blue left border (for key results)"""

PATTERN = """\
EQUATION (KaTeX formulas, step-by-step derivation, math proofs):
  // Equation inside mainZone (NEVER use zone-eq — it overlaps with other zones):
  // Use 'katex' (1.4em) when sharing space with other content (heatmap, grid, etc.)
  // Use 'katex-lg' (1.8em) only when the equation is the MAIN focus of the step
  // Use 'katex-xl' (2.4em) only for a single standalone equation
  const eqCard = document.createElement('div');
  eqCard.className = 'card card-accent';
  eqCard.style.cssText = 'padding:8px 16px; text-align:center;';
  const eqInner = document.createElement('div');
  eqInner.className = 'katex';
  katex.render('E = mc^2', eqInner, {{throwOnError:false, displayMode:true}});
  eqCard.appendChild(eqInner);
  mainZone.appendChild(eqCard);

  // CRITICAL: In JS strings, LaTeX backslashes must be DOUBLED:
  //   '\\\\frac{{a}}{{b}}'   ← correct (renders as fraction)
  //   '\\frac{{a}}{{b}}'    ← WRONG (JS eats the backslash)
  //   Use {{}} for literal braces in template strings inside Python

  // Step-by-step derivation (cards stacking in mainZone):
  const steps = [
    '\\\\nabla_\\\\theta J(\\\\theta) = \\\\frac{{1}}{{m}} \\\\sum_{{i=1}}^{{m}} \\\\nabla_\\\\theta L(f(x_i), y_i)',
    '= \\\\frac{{1}}{{m}} \\\\sum_{{i=1}}^{{m}} (\\\\hat{{y}}_i - y_i) \\\\cdot x_i',
    '\\\\theta \\\\leftarrow \\\\theta - \\\\alpha \\\\nabla_\\\\theta J(\\\\theta)',
  ];
  const stepEls = steps.map((tex, i) => {{
    const card = document.createElement('div');
    card.className = i === steps.length - 1 ? 'card card-accent' : 'card';
    card.style.cssText = 'padding:12px 20px; margin:6px 0;';
    const eq = document.createElement('div');
    eq.className = 'katex-lg';
    katex.render(tex, eq, {{throwOnError:false, displayMode:true}});
    card.appendChild(eq);
    mainZone.appendChild(card);
    return card;
  }});
  gsap.set(stepEls, {{opacity:0, x:-30}});

  // Reveal steps one by one with slide-in:
  tl.to(stepEls[0], {{opacity:1, x:0, duration:0.8, ease:'power2.out'}}, 'step-1');
  tl.to(stepEls[1], {{opacity:1, x:0, duration:0.8, ease:'power2.out'}}, 'step-2');
  tl.to(stepEls[2], {{opacity:1, x:0, duration:0.8, ease:'power2.out'}}, 'step-3');
  // Highlight final result:
  tl.to(stepEls[2], {{boxShadow:'0 0 16px rgba(56,139,253,0.4)', duration:0.6}}, 'step-3+=1');

  // Color-code formula terms (wrap term in span, animate color):
  // In the KaTeX output, find elements by class and color them:
  const colorTerm = (container, cssClass, color) => {{
    container.querySelectorAll(cssClass).forEach(el => {{
      gsap.set(el, {{color: '#c9d1d9'}});  // start neutral
    }});
    // Then animate:
    tl.to(container.querySelectorAll(cssClass), {{color, duration:0.5}}, 'color-terms');
  }};

  // Annotation below equation (inside mainZone, not zone-annotation):
  const annotDiv = document.createElement('div');
  annotDiv.className = 'subtitle';
  annotDiv.style.cssText = 'margin-top:8px;';
  annotDiv.textContent = 'where α is the learning rate';
  mainZone.appendChild(annotDiv);"""
