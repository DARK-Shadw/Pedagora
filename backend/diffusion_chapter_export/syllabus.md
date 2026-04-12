# Diffusion Course — Syllabus

**Title:** Diffusion Models to Video Generation: Build It from Scratch

**Description:** A visual-first, hands-on journey from probability foundations through cutting-edge video diffusion models. By the end, you'll have built a working text-to-video generation pipeline from scratch — understanding every equation, every architectural choice, and every line of code.

**Total minutes:** 690

**Difficulty:** beginner -> intermediate -> advanced


## mod1 — The Math That Powers Magic
_Lock in the probability, statistics, and CNN intuition that every generative model is secretly built on. Visually-driven — no formula without a picture._

Estimated: 125 min

### mod1-les1 — Why Randomness is Everything: Probability & Distributions for Generative AI
- **Type:** visualization
- **Minutes:** 40
- **Objectives:**
  - Explain Gaussian distributions, KL divergence, and conditional probability using visual intuition
  - Interpret probability density functions and what 'sampling from a distribution' means geometrically
  - Connect Bayes' theorem to how generative models reason about data
- **Topics:** Probability & Statistics for Deep Learning

### mod1-les2 — The Convolution Superpower: CNNs That See at Every Scale
- **Type:** visualization
- **Minutes:** 40
- **Objectives:**
  - Illustrate how convolution filters detect edges, textures, and high-level patterns layer by layer
  - Explain spatial downsampling, residual connections, and GroupNorm in modern CNN blocks
  - Compare feature map resolutions — show how shallow layers see edges, deep layers see semantics
- **Topics:** CNN Architecture & Deep Learning Components
- **Prereqs:** mod1-les1

### mod1-les3 — Training Machines to Learn: Backprop & Optimization Demystified
- **Type:** practice
- **Minutes:** 45
- **Objectives:**
  - Implement a manual forward + backward pass in PyTorch to solidify gradient intuition
  - Compare Adam, SGD, and cosine LR scheduling using live loss curve visualization
  - Diagnose vanishing/exploding gradients and apply gradient clipping and normalization fixes
- **Topics:** Deep Learning Training Loop Mastery
- **Prereqs:** mod1-les2

## mod2 — Teaching Machines to Create
_Understand the generative model family tree — VAEs, GANs, and temporal networks — that set the stage for diffusion. Build latent space intuition and learn why sequence modeling is the key to video._

Estimated: 130 min

### mod2-les1 — The Compression Secret: VAEs and the Geometry of Latent Space
- **Type:** visualization
- **Minutes:** 45
- **Objectives:**
  - Explain the encoder-decoder structure and the ELBO objective with visual intuition
  - Describe why the reparameterization trick enables backprop through stochastic sampling
  - Visualize and interpret a trained VAE's latent space — interpolation paths, clusters, and disentanglement
- **Topics:** Generative Model Foundations: VAEs & GANs
- **Prereqs:** mod1-les1, mod1-les3

### mod2-les2 — The Adversarial Game: GANs Learning to Hallucinate Reality
- **Type:** theory
- **Minutes:** 40
- **Objectives:**
  - Explain the generator-discriminator minimax game using game theory intuition
  - Identify GAN failure modes — mode collapse, training instability — and how WGAN-GP addresses them
  - Compare VAE vs GAN quality trade-offs and articulate when each is preferable
- **Topics:** Generative Model Foundations: VAEs & GANs
- **Prereqs:** mod2-les1

### mod2-les3 — Time Traveling Networks: How Models Learn Motion & Sequences
- **Type:** theory
- **Minutes:** 45
- **Objectives:**
  - Explain temporal self-attention and how it captures long-range dependencies across frames
  - Compare RNN/LSTM vs Transformer approaches — and argue why Transformers dominate for video
  - Apply positional encoding intuition to understand how models know 'when' in a sequence
- **Topics:** Temporal Modeling & Sequential Data in Deep Learning
- **Prereqs:** mod1-les2, mod2-les2

## mod3 — Noise to Masterpiece: Diffusion Model Fundamentals
_Understand how DDPM systematically destroys images and learns to reverse the process — then build and train one from scratch. Unlock faster sampling with DDIM and score matching._

Estimated: 130 min

### mod3-les1 — Corrupting to Learn: The Forward Process & Noise Schedules
- **Type:** visualization
- **Minutes:** 45
- **Objectives:**
  - Explain the DDPM forward process q(x_t|x_0) and derive the closed-form marginal that makes training tractable
  - Visualize how linear vs cosine noise schedules degrade images differently across 1000 timesteps
  - Distinguish what the model actually learns to predict — noise ε vs original image x_0
- **Topics:** Diffusion Model Fundamentals (DDPM)
- **Prereqs:** mod2-les1, mod2-les3

### mod3-les2 — Reversing Chaos: Training the Denoising Network from Scratch
- **Type:** practice
- **Minutes:** 45
- **Objectives:**
  - Implement the DDPM training objective and explain noise prediction vs x_0 prediction equivalence
  - Build a U-Net denoiser with timestep conditioning in PyTorch from scratch
  - Train a DDPM on MNIST and visualize the full denoising trajectory from pure noise to digit
- **Topics:** Diffusion Model Fundamentals (DDPM)
- **Prereqs:** mod3-les1

### mod3-les3 — Speed Without Sacrifice: DDIM, Score Matching & Smarter Sampling
- **Type:** theory
- **Minutes:** 40
- **Objectives:**
  - Explain DDIM's deterministic non-Markovian sampling and why it enables 10–50× speedup
  - Connect the denoising network to the score function ∇_x log p_t(x) via Tweedie's formula
  - Compare DDPM, DDIM, and DPM-Solver on the speed vs quality frontier
- **Topics:** Improved Sampling: DDIM, Score Matching & Noise Schedules
- **Prereqs:** mod3-les2

## mod4 — The Architecture of Dreams: Latent Diffusion & U-Net Mastery
_Discover how Stable Diffusion compresses images into latent space before diffusing — and master the attention-augmented U-Net that makes high-resolution generation tractable._

Estimated: 130 min

### mod4-les1 — Compress Then Create: How Latent Diffusion Breaks the Compute Wall
- **Type:** theory
- **Minutes:** 40
- **Objectives:**
  - Explain why pixel-space diffusion is compute-prohibitive and how LDMs solve it via perceptual compression
  - Describe the two-stage LDM pipeline: train a VQ-VAE encoder, then diffuse in its latent space
  - Compare LDM vs pixel diffusion on FID, memory footprint, and generation speed
- **Topics:** Latent Diffusion Models & U-Net Architecture
- **Prereqs:** mod3-les3

### mod4-les2 — The U-Net Inside Every Diffusion Model: Skip Connections, Attention & Conditioning
- **Type:** visualization
- **Minutes:** 45
- **Objectives:**
  - Trace the U-Net encoder-decoder path and explain why skip connections preserve spatial detail
  - Implement self-attention and cross-attention blocks inside U-Net residual layers
  - Explain timestep and text conditioning injection via AdaGN and cross-attention
- **Topics:** Latent Diffusion Models & U-Net Architecture
- **Prereqs:** mod4-les1

### mod4-les3 — Conditioning the Dream: Text Control & Classifier-Free Guidance
- **Type:** practice
- **Minutes:** 45
- **Objectives:**
  - Implement classifier-free guidance for conditional image generation from scratch
  - Integrate a CLIP text encoder to condition the U-Net on text prompts via cross-attention
  - Evaluate conditional generation quality using FID and CLIP similarity scores
- **Topics:** Latent Diffusion Models & U-Net Architecture
- **Prereqs:** mod4-les2

## mod5 — Lights, Camera, Diffusion: Building Video Generation from Scratch
_Extend everything you've built to video — temporal attention, 3D convolutions, and a full end-to-end text-to-video pipeline. Final project: a working video generation model you designed._

Estimated: 175 min

### mod5-les1 — Frames That Flow: Temporal Attention for Motion Consistency
- **Type:** theory
- **Minutes:** 45
- **Objectives:**
  - Explain how temporal self-attention enables frames to communicate across time for motion coherence
  - Compare factorized spatial-temporal attention vs full 3D attention on compute and quality trade-offs
  - Describe how Video Diffusion Models extend DDPM to video with joint noise across all frames
- **Topics:** Video Diffusion Models: Temporal Attention & 3D Architectures
- **Prereqs:** mod4-les3

### mod5-les2 — Into the Third Dimension: 3D U-Net & Spatiotemporal Convolutions
- **Type:** visualization
- **Minutes:** 40
- **Objectives:**
  - Implement pseudo-3D convolutions (2D spatial + 1D temporal) as an efficient alternative to full 3D
  - Explain how inflated 3D convolutions extend a pretrained image U-Net to video with minimal new parameters
  - Design a 3D U-Net that processes video clips as (T, H, W, C) spatiotemporal volumes
- **Topics:** Video Diffusion Models: Temporal Attention & 3D Architectures
- **Prereqs:** mod5-les1

### mod5-les3 — Your First Video Diffusion Model: Architecture to Training Loop
- **Type:** practice
- **Minutes:** 45
- **Objectives:**
  - Assemble a complete video U-Net: 3D ResBlocks, temporal attention, spatial attention
  - Implement the video diffusion training loop with (B, T, C, H, W) tensor batches
  - Train on a short video dataset and debug temporal flickering using consistency regularization
- **Topics:** Building a Video Generation Pipeline from Scratch
- **Prereqs:** mod5-les2

### mod5-les4 — Ship It: The Complete Text-to-Video Generation Pipeline
- **Type:** practice
- **Minutes:** 45
- **Objectives:**
  - Integrate CLIP text conditioning into the video U-Net for text-to-video generation
  - Implement DDIM sampling over video frames for fast generation (50 steps vs 1000)
  - Evaluate generated videos with FVD (Fréchet Video Distance) and build an end-to-end generation script
- **Topics:** Building a Video Generation Pipeline from Scratch
- **Prereqs:** mod5-les3
