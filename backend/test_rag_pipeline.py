"""End-to-end test for the RAG pipeline components.

Tests: parser (PDF + PPTX), chunker, embeddings (if JINA_API_KEY set), and figure extraction.
Run: python test_rag_pipeline.py
"""

import asyncio
import sys
import os
import json
import time

# Fix Windows console encoding for Unicode chars in PDF content
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Fix HuggingFace symlink issues on Windows (Docling model downloads)
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

TEST_DIR = os.path.join(os.path.dirname(__file__), "_test_materials")


def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


async def test_parser_pdf():
    """Test Docling parser on the DDPM paper."""
    separator("TEST 1: PDF Parser (DDPM Paper)")
    from app.resources.parser import parse_document

    pdf_path = os.path.join(TEST_DIR, "denoising_diffusion.pdf")
    if not os.path.exists(pdf_path):
        print("SKIP: denoising_diffusion.pdf not found")
        return None

    print(f"Parsing: {pdf_path} ({os.path.getsize(pdf_path) / 1024 / 1024:.1f} MB)")
    start = time.time()
    parsed = await parse_document(pdf_path, "pdf")
    elapsed = time.time() - start

    print(f"Parse time: {elapsed:.1f}s")
    print(f"Sections: {len(parsed.sections)}")
    print(f"Figures: {len(parsed.figures)}")
    print(f"Page count: {parsed.page_count}")

    if parsed.toc:
        print(f"TOC entries: {len(parsed.toc.get('sections', []))}")
        for entry in parsed.toc.get("sections", [])[:8]:
            print(f"  L{entry['level']}: {entry['title'][:80]}")

    print("\nFirst 5 sections:")
    for i, sec in enumerate(parsed.sections[:5]):
        content_preview = (sec.content or "")[:120].replace("\n", " ")
        print(f"  [{i}] L{sec.level} '{sec.title[:60]}' (page {sec.page_start})")
        print(f"       Content: {content_preview}...")

    if parsed.figures:
        print(f"\nFirst 3 figures:")
        for i, fig in enumerate(parsed.figures[:3]):
            print(f"  [{i}] page={fig.page_number}, caption='{fig.caption}', size={len(fig.image_bytes)} bytes, type={fig.figure_type}")

    return parsed


async def test_parser_pptx():
    """Test python-pptx parser on the tutorial."""
    separator("TEST 2: PPTX Parser (Diffusion Tutorial)")
    from app.resources.parser import parse_document

    pptx_path = os.path.join(TEST_DIR, "diffusion_tutorial.pptx")
    if not os.path.exists(pptx_path):
        print("SKIP: diffusion_tutorial.pptx not found")
        return None

    print(f"Parsing: {pptx_path} ({os.path.getsize(pptx_path) / 1024:.1f} KB)")
    start = time.time()
    parsed = await parse_document(pptx_path, "pptx")
    elapsed = time.time() - start

    print(f"Parse time: {elapsed:.1f}s")
    print(f"Sections (slides): {len(parsed.sections)}")
    print(f"Figures: {len(parsed.figures)}")
    print(f"Page count (slides): {parsed.page_count}")

    print("\nAll slides:")
    for i, sec in enumerate(parsed.sections):
        content_preview = (sec.content or "")[:150].replace("\n", " | ")
        print(f"  [Slide {sec.page_start}] '{sec.title}'")
        print(f"    Content: {content_preview}")

    return parsed


async def test_chunker(parsed_pdf, parsed_pptx):
    """Test structure-aware chunker on parsed documents."""
    separator("TEST 3: Chunker")
    from app.resources.chunker import chunk_sections

    results = {}

    if parsed_pdf:
        print("--- Chunking PDF (DDPM Paper) ---")
        start = time.time()
        chunks = chunk_sections(parsed_pdf.sections, "denoising_diffusion.pdf")
        elapsed = time.time() - start
        print(f"Chunks: {len(chunks)} (from {len(parsed_pdf.sections)} sections)")
        print(f"Chunk time: {elapsed:.3f}s")

        # Stats
        token_counts = [c.token_count for c in chunks]
        if token_counts:
            print(f"Token count: min={min(token_counts)}, max={max(token_counts)}, avg={sum(token_counts)/len(token_counts):.0f}")

        print("\nFirst 5 chunks:")
        for i, chunk in enumerate(chunks[:5]):
            print(f"  [{i}] tokens={chunk.token_count}, page={chunk.page_number}")
            print(f"       Prefix: {chunk.context_prefix}")
            print(f"       Content: {chunk.content[:120].replace(chr(10), ' ')}...")

        # Check for formula preservation
        formula_chunks = [c for c in chunks if "$$" in c.content or "\\begin{" in c.content]
        table_chunks = [c for c in chunks if c.content.count("|") > 4]
        print(f"\nFormula chunks (preserved intact): {len(formula_chunks)}")
        print(f"Table chunks (preserved intact): {len(table_chunks)}")

        results["pdf_chunks"] = chunks

    if parsed_pptx:
        print("\n--- Chunking PPTX (Diffusion Tutorial) ---")
        start = time.time()
        chunks = chunk_sections(parsed_pptx.sections, "diffusion_tutorial.pptx")
        elapsed = time.time() - start
        print(f"Chunks: {len(chunks)} (from {len(parsed_pptx.sections)} slides)")
        print(f"Chunk time: {elapsed:.3f}s")

        print("\nAll chunks:")
        for i, chunk in enumerate(chunks):
            print(f"  [{i}] tokens={chunk.token_count}, page={chunk.page_number}")
            print(f"       Prefix: {chunk.context_prefix}")
            print(f"       Content: {chunk.content[:100].replace(chr(10), ' ')}...")

        results["pptx_chunks"] = chunks

    return results


async def test_embeddings(chunks_dict):
    """Test Jina embeddings on a sample of chunks."""
    separator("TEST 4: Jina Embeddings")

    # Check for API key
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

    jina_key = os.environ.get("JINA_API_KEY", "")
    if not jina_key:
        print("SKIP: JINA_API_KEY not set in environment")
        print("Set it in backend/.env to test embeddings")
        return None

    from app.services.embeddings import embed_texts, embed_query

    # Take a sample of chunks
    all_chunks = []
    for key, chunks in chunks_dict.items():
        all_chunks.extend(chunks[:5])  # 5 from each source

    if not all_chunks:
        print("SKIP: No chunks available for embedding")
        return None

    sample_texts = [f"{c.context_prefix}\n{c.content}" for c in all_chunks]
    print(f"Embedding {len(sample_texts)} sample chunks...")

    start = time.time()
    embeddings = await embed_texts(sample_texts)
    elapsed = time.time() - start

    print(f"Embed time: {elapsed:.2f}s ({elapsed/len(sample_texts)*1000:.0f}ms per chunk)")
    print(f"Embedding count: {len(embeddings)}")
    if embeddings:
        print(f"Embedding dimension: {len(embeddings[0])}")
        print(f"First embedding (first 10 values): {embeddings[0][:10]}")

        # Test similarity between related chunks
        import math

        def cosine_sim(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a))
            nb = math.sqrt(sum(x * x for x in b))
            return dot / (na * nb) if na and nb else 0

        if len(embeddings) >= 2:
            sim_01 = cosine_sim(embeddings[0], embeddings[1])
            sim_0last = cosine_sim(embeddings[0], embeddings[-1])
            print(f"\nSimilarity chunk[0] vs chunk[1]: {sim_01:.4f}")
            print(f"Similarity chunk[0] vs chunk[{len(embeddings)-1}]: {sim_0last:.4f}")

    # Test query embedding
    print("\n--- Query Embedding ---")
    start = time.time()
    query_emb = await embed_query("How does the reverse diffusion process work?")
    elapsed = time.time() - start
    print(f"Query embed time: {elapsed:.3f}s")
    print(f"Query embedding dimension: {len(query_emb)}")

    # Rank chunks by similarity to query
    if embeddings:
        import math

        def cosine_sim(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a))
            nb = math.sqrt(sum(x * x for x in b))
            return dot / (na * nb) if na and nb else 0

        scored = []
        for i, emb in enumerate(embeddings):
            sim = cosine_sim(query_emb, emb)
            scored.append((sim, i, all_chunks[i]))

        scored.sort(reverse=True)
        print(f"\nTop 3 chunks for query 'How does the reverse diffusion process work?':")
        for sim, idx, chunk in scored[:3]:
            print(f"  [{idx}] sim={sim:.4f} | {chunk.content[:100].replace(chr(10), ' ')}...")

    return embeddings


async def test_figure_extraction(parsed_pdf):
    """Test VLM figure description on extracted figures."""
    separator("TEST 5: Figure Description (VLM)")

    if not parsed_pdf or not parsed_pdf.figures:
        print("SKIP: No figures available from parsed PDF")
        return

    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not openrouter_key:
        print("SKIP: OPENROUTER_API_KEY not set — VLM requires OpenRouter")
        print(f"But we extracted {len(parsed_pdf.figures)} figures from the PDF:")
        for i, fig in enumerate(parsed_pdf.figures[:5]):
            print(f"  [{i}] page={fig.page_number}, size={len(fig.image_bytes)} bytes")
        return

    from app.resources.figures import describe_figure

    # Test on first 2 figures
    for i, fig in enumerate(parsed_pdf.figures[:2]):
        print(f"\n--- Figure {i+1} (page {fig.page_number}, {len(fig.image_bytes)} bytes) ---")
        start = time.time()
        result = await describe_figure(
            image_bytes=fig.image_bytes,
            caption=fig.caption,
            context="From DDPM paper on denoising diffusion probabilistic models",
        )
        elapsed = time.time() - start
        print(f"VLM time: {elapsed:.2f}s")
        print(f"Description: {result.description}")
        print(f"Concepts: {result.concepts}")
        print(f"Figure type: {result.figure_type}")


async def test_parser_pdf_2():
    """Test parser on second PDF (Stable Diffusion / LDM)."""
    separator("TEST 6: PDF Parser (Stable Diffusion / LDM Paper)")
    from app.resources.parser import parse_document

    pdf_path = os.path.join(TEST_DIR, "stable_diffusion_ldm.pdf")
    if not os.path.exists(pdf_path):
        print("SKIP: stable_diffusion_ldm.pdf not found")
        return None

    print(f"Parsing: {pdf_path} ({os.path.getsize(pdf_path) / 1024 / 1024:.1f} MB)")
    start = time.time()
    parsed = await parse_document(pdf_path, "pdf")
    elapsed = time.time() - start

    print(f"Parse time: {elapsed:.1f}s")
    print(f"Sections: {len(parsed.sections)}")
    print(f"Figures: {len(parsed.figures)}")
    print(f"Page count: {parsed.page_count}")

    if parsed.toc:
        print(f"TOC entries: {len(parsed.toc.get('sections', []))}")
        for entry in parsed.toc.get("sections", [])[:8]:
            print(f"  L{entry['level']}: {entry['title'][:80]}")

    print(f"\nFirst 5 sections:")
    for i, sec in enumerate(parsed.sections[:5]):
        content_preview = (sec.content or "")[:120].replace("\n", " ")
        print(f"  [{i}] L{sec.level} '{sec.title[:60]}' (page {sec.page_start})")
        print(f"       Content: {content_preview}...")

    return parsed


async def main():
    print("=" * 60)
    print("  PEDAGORA RAG PIPELINE — END-TO-END TEST")
    print("=" * 60)
    print(f"\nTest materials dir: {TEST_DIR}")
    print(f"Files: {os.listdir(TEST_DIR)}")

    # Test 1: PDF parser
    parsed_pdf = None
    try:
        parsed_pdf = await test_parser_pdf()
    except Exception as e:
        print(f"FAILED: {e}")
        print("(Docling may not be installed — continuing with other tests)")

    # Test 2: PPTX parser
    parsed_pptx = None
    try:
        parsed_pptx = await test_parser_pptx()
    except Exception as e:
        print(f"FAILED: {e}")

    # Test 3: Chunker
    chunks_dict = {}
    try:
        chunks_dict = await test_chunker(parsed_pdf, parsed_pptx) or {}
    except Exception as e:
        print(f"FAILED: {e}")

    # Test 4: Embeddings (requires JINA_API_KEY)
    embeddings = None
    try:
        embeddings = await test_embeddings(chunks_dict)
    except Exception as e:
        print(f"FAILED: {e}")

    # Test 5: Figure extraction (requires OPENROUTER_API_KEY)
    try:
        await test_figure_extraction(parsed_pdf)
    except Exception as e:
        print(f"FAILED: {e}")

    # Test 6: Second PDF
    parsed_pdf_2 = None
    try:
        parsed_pdf_2 = await test_parser_pdf_2()
    except Exception as e:
        print(f"FAILED: {e}")

    separator("SUMMARY")
    results = {
        "pdf_sections": len(parsed_pdf.sections) if parsed_pdf else 0,
        "pdf_figures": len(parsed_pdf.figures) if parsed_pdf else 0,
        "pdf_pages": parsed_pdf.page_count if parsed_pdf else 0,
        "pptx_sections": len(parsed_pptx.sections) if parsed_pptx else 0,
        "pdf_chunks": len(chunks_dict.get("pdf_chunks", [])) if chunks_dict else 0,
        "pptx_chunks": len(chunks_dict.get("pptx_chunks", [])) if chunks_dict else 0,
        "embeddings_tested": len(embeddings) if embeddings else 0,
        "pdf2_sections": len(parsed_pdf_2.sections) if parsed_pdf_2 else 0,
        "pdf2_figures": len(parsed_pdf_2.figures) if parsed_pdf_2 else 0,
    }

    for k, v in results.items():
        status = "OK" if v > 0 else "SKIP/EMPTY"
        print(f"  {k}: {v} ({status})")

    print(f"\nTotal chunks: {results['pdf_chunks'] + results['pptx_chunks']}")
    print(f"Total figures: {results['pdf_figures'] + results.get('pdf2_figures', 0)}")

    if embeddings:
        print(f"Embeddings: {len(embeddings)} vectors of dim {len(embeddings[0])}")
    else:
        print("Embeddings: SKIPPED (set JINA_API_KEY in .env)")


if __name__ == "__main__":
    asyncio.run(main())
