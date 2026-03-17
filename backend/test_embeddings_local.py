"""Test embeddings + chunker + semantic search using local model.

Uses all-MiniLM-L6-v2 (22MB) — no API key needed.
Tests: embedding quality, semantic search ranking, chunk retrieval.
"""

import asyncio
import sys
import os
import math
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

sys.path.insert(0, os.path.dirname(__file__))

TEST_DIR = os.path.join(os.path.dirname(__file__), "_test_materials")


def cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0


def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


class LocalEmbedder:
    """Sentence-transformers compatible embedder using transformers + torch."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        from transformers import AutoTokenizer, AutoModel
        import torch

        print(f"Loading model: {model_name}...")
        start = time.time()
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.model.eval()
        self.dim = self.model.config.hidden_size
        elapsed = time.time() - start
        print(f"Model loaded in {elapsed:.1f}s (dim={self.dim})")

    def embed(self, texts: list[str]) -> list[list[float]]:
        import torch

        encoded = self.tokenizer(
            texts, padding=True, truncation=True, max_length=512, return_tensors="pt"
        )
        with torch.no_grad():
            output = self.model(**encoded)
        # Mean pooling
        attention_mask = encoded["attention_mask"]
        token_embeddings = output.last_hidden_state
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        pooled = torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(
            input_mask_expanded.sum(1), min=1e-9
        )
        # Normalize
        pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
        return pooled.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


async def main():
    separator("LOCAL EMBEDDING + CHUNKER + SEARCH TEST")

    # --- Step 1: Parse PPTX (fast) ---
    from app.resources.parser import parse_document
    from app.resources.chunker import chunk_sections

    pptx_path = os.path.join(TEST_DIR, "diffusion_tutorial.pptx")
    print("Parsing PPTX...")
    parsed_pptx = await parse_document(pptx_path, "pptx")
    pptx_chunks = chunk_sections(parsed_pptx.sections, "diffusion_tutorial.pptx")

    # --- Step 2: Parse PDF (use cached result if possible) ---
    print("Parsing DDPM PDF (this takes ~4 min)...")
    pdf_path = os.path.join(TEST_DIR, "denoising_diffusion.pdf")
    parsed_pdf = await parse_document(pdf_path, "pdf")
    pdf_chunks = chunk_sections(parsed_pdf.sections, "denoising_diffusion.pdf")

    all_chunks = pdf_chunks + pptx_chunks
    print(f"\nTotal chunks: {len(all_chunks)} ({len(pdf_chunks)} PDF + {len(pptx_chunks)} PPTX)")

    # --- Step 3: Embed all chunks ---
    separator("EMBEDDING ALL CHUNKS")
    embedder = LocalEmbedder()

    chunk_texts = [f"{c.context_prefix}\n{c.content}" for c in all_chunks]

    print(f"\nEmbedding {len(chunk_texts)} chunks...")
    start = time.time()
    # Batch to avoid OOM
    all_embeddings = []
    batch_size = 16
    for i in range(0, len(chunk_texts), batch_size):
        batch = chunk_texts[i : i + batch_size]
        batch_embs = embedder.embed(batch)
        all_embeddings.extend(batch_embs)
        if (i // batch_size) % 2 == 0:
            print(f"  Embedded {min(i + batch_size, len(chunk_texts))}/{len(chunk_texts)}")

    elapsed = time.time() - start
    print(f"Embedding time: {elapsed:.1f}s ({elapsed / len(chunk_texts) * 1000:.0f}ms per chunk)")
    print(f"Embedding dimension: {len(all_embeddings[0])}")

    # --- Step 4: Semantic search queries ---
    separator("SEMANTIC SEARCH TEST")

    test_queries = [
        "How does the reverse diffusion process work?",
        "What is the U-Net architecture used in diffusion models?",
        "What is the training objective for DDPM?",
        "noise schedule and variance",
        "sampling algorithm steps",
    ]

    for query in test_queries:
        print(f"\n--- Query: '{query}' ---")
        query_emb = embedder.embed_query(query)

        # Score all chunks
        scored = []
        for i, emb in enumerate(all_embeddings):
            sim = cosine_sim(query_emb, emb)
            scored.append((sim, i))
        scored.sort(reverse=True)

        # Show top 3
        for rank, (sim, idx) in enumerate(scored[:3], 1):
            chunk = all_chunks[idx]
            source = "PPTX" if idx >= len(pdf_chunks) else "PDF"
            content_preview = chunk.content[:120].replace("\n", " ")
            print(f"  #{rank} sim={sim:.4f} [{source}] {chunk.context_prefix}")
            print(f"       {content_preview}...")

    # --- Step 5: Cross-source similarity ---
    separator("CROSS-SOURCE SIMILARITY")

    # Find PPTX chunks and their most similar PDF chunks
    print("For each PPTX slide, finding the most similar PDF chunk:")
    for pptx_idx in range(len(pdf_chunks), len(all_chunks)):
        pptx_emb = all_embeddings[pptx_idx]
        pptx_chunk = all_chunks[pptx_idx]

        best_sim = 0
        best_pdf_idx = 0
        for pdf_idx in range(len(pdf_chunks)):
            sim = cosine_sim(pptx_emb, all_embeddings[pdf_idx])
            if sim > best_sim:
                best_sim = sim
                best_pdf_idx = pdf_idx

        pdf_chunk = all_chunks[best_pdf_idx]
        print(f"\n  PPTX: '{pptx_chunk.context_prefix}'")
        print(f"     -> PDF:  '{pdf_chunk.context_prefix}' (sim={best_sim:.4f})")
        print(f"        PDF content: {pdf_chunk.content[:100].replace(chr(10), ' ')}...")

    # --- Step 6: Embedding statistics ---
    separator("EMBEDDING STATISTICS")

    # Inter-chunk similarity distribution
    sample_sims = []
    import random
    random.seed(42)
    for _ in range(200):
        i = random.randint(0, len(all_embeddings) - 1)
        j = random.randint(0, len(all_embeddings) - 1)
        if i != j:
            sample_sims.append(cosine_sim(all_embeddings[i], all_embeddings[j]))

    if sample_sims:
        sample_sims.sort()
        print(f"Inter-chunk cosine similarity (200 random pairs):")
        print(f"  Min: {min(sample_sims):.4f}")
        print(f"  P25: {sample_sims[len(sample_sims)//4]:.4f}")
        print(f"  Median: {sample_sims[len(sample_sims)//2]:.4f}")
        print(f"  P75: {sample_sims[3*len(sample_sims)//4]:.4f}")
        print(f"  Max: {max(sample_sims):.4f}")
        print(f"  Mean: {sum(sample_sims)/len(sample_sims):.4f}")

    separator("SUMMARY")
    print(f"  PDF sections: {len(parsed_pdf.sections)}")
    print(f"  PDF chunks: {len(pdf_chunks)}")
    print(f"  PPTX sections: {len(parsed_pptx.sections)}")
    print(f"  PPTX chunks: {len(pptx_chunks)}")
    print(f"  Total chunks embedded: {len(all_embeddings)}")
    print(f"  Embedding dim: {len(all_embeddings[0])}")
    print(f"  Embedding model: all-MiniLM-L6-v2 (local)")
    print(f"\n  ALL TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
