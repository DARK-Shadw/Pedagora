# RAG Deep Research: User-Uploaded Document Handling for Pedagora

**Date**: March 2026

## Final Recommendation: Hybrid RAG with Structure-Aware Chunking

### Architecture Stack (All Free/Open-Source)

| Component | Choice | Why |
|---|---|---|
| Document Parser | **Docling** (MIT) | Best math/table handling (97.9% table accuracy), multi-format (PDF, PPTX, DOCX), LaTeX formula extraction |
| Embedding Model | **nomic-embed-text-v1.5** (local, CPU) | Free, 768d, 8192 token context, Apache-2.0 |
| Vector Store | **Supabase pgvector** (HNSW) | Already in stack, RLS for multi-tenant, hybrid search capable |
| Keyword Search | **Supabase tsvector** | Built into PostgreSQL, no extra infra |
| Fusion | **Reciprocal Rank Fusion (RRF)** | Simple, effective, runs in SQL |
| Reranker | **ms-marco-MiniLM-L-6-v2** (CPU) | Free, fast (~30-50ms), no GPU needed |
| Chunking | **Structure-aware recursive** | Preserves educational document hierarchy |
| Context | **Deterministic prefix** (no LLM) | Free alternative to Anthropic's Contextual Retrieval |

### Cost: $0 API fees, $7/mo Render (1GB RAM tier needed)

---

## Approach Comparison

### 1. Naive RAG — NOT SUITABLE
- Destroys document structure, splits formulas, loses context
- Only useful as one signal in a hybrid system

### 2. ColPali / PageIndex — NOT PRACTICAL YET
- Treats pages as images, handles diagrams natively
- Requires GPU, storage-heavy, immature for production
- Monitor for when VLM inference becomes cheaper

### 3. GraphRAG / Knowledge Graphs
- **Microsoft GraphRAG**: Excellent for concept relationships but massive LLM token consumption (3-5x baseline)
- **LightRAG** (HKUDS): Lightweight alternative, 30% lower latency, incremental updates, has FastAPI server
- Both require too many LLM calls for free-tier constraints
- Better as Phase 3 enhancement

### 4. Hybrid RAG (Vector + BM25 + Reranking) — RECOMMENDED
- **Benchmarks**: 91% accuracy with reranking (vs 58% BM25-only, 79% hybrid without reranking)
- BM25 catches exact terms (theorem names, notation) that embeddings miss
- Vector search catches semantic matches that keywords miss
- Works with Supabase's existing tsvector + pgvector
- No additional infrastructure

### 5. Contextual Retrieval (Anthropic's approach)
- Reduces failed retrievals by 49%, with reranking by 67%
- Cost-prohibitive: every chunk needs LLM call with full document context
- **Free alternative**: deterministic prefix from document structure (section title + heading hierarchy + page number) captures ~60% of benefit

### 6. Late Chunking
- Embeds full document first, then chunks embeddings
- Requires specific long-context embedding model
- Marginal improvement over contextual retrieval + reranking

---

## Document Parsing Comparison

| Tool | Formats | Math/LaTeX | Tables | Speed | License |
|------|---------|------------|--------|-------|---------|
| **Docling** | PDF, DOCX, PPTX, XLSX, HTML, images | Excellent (inline + display → LaTeX) | 97.9% accuracy | Medium | MIT |
| Marker | PDF | Good (with --force_ocr) | Good | Medium (11.3s/doc) | GPL-3.0 |
| PyMuPDF4LLM | PDF | No advanced math | Basic | Fast (0.12s/doc) | AGPL-3.0 |
| LlamaParse | PDF, DOCX, PPTX | Good | Good | Fast (~6s) | Proprietary (1000 pages/day free) |
| Unstructured | PDF, DOCX, PPTX, HTML | Limited | 75% complex tables | Medium | Apache-2.0 |

**Winner: Docling** — MIT license, native PPTX support, best math/table handling, runs on CPU

---

## Embedding Models Comparison

| Model | Dims | Context | License | Cost |
|-------|------|---------|---------|------|
| **nomic-embed-text-v1.5** | 768 (MRL: 256-768) | 8192 tokens | Apache-2.0 | Free (local) |
| all-MiniLM-L6-v2 | 384 | 256 tokens | Apache-2.0 | Free (too short context) |
| BGE-base-en-v1.5 | 768 | 512 tokens | MIT | Free |
| gemini-embedding-001 | 3072 | 2048 tokens | API | Free: 1000 RPD |

**Winner: nomic-embed-text-v1.5** — 8192 token context covers large chunks, ~262MB model, runs on CPU

**Note**: Pollinations does NOT offer an embedding endpoint.

---

## Supabase pgvector Performance

| Documents | Chunks | Query Latency |
|---|---|---|
| 10 | ~500 | ~15ms |
| 100 | ~5,000 | ~25ms |
| 1,000 | ~50,000 | ~85ms |
| 10,000 | ~500,000 | ~250ms |

Use HNSW indexes (not IVFFlat) — no training step, better speed-recall, handles incremental inserts.

---

## Chunking Strategy

1. Parse with Docling → structured elements with hierarchy
2. Group elements by section (heading + children)
3. Recursive character splitting within sections, respecting element boundaries
4. Preserve special elements intact:
   - Tables: complete Markdown tables (never split)
   - Formulas: with surrounding context sentence
   - Code blocks: complete
   - Figures: stored separately, caption as searchable content
5. Deterministic context prefix: `[Document: {filename}] [Section: {hierarchy}] [Page: {page}]`

Parameters: 512 tokens chunk size, 64 tokens overlap (12.5%), 100 tokens minimum

---

## SQL: Hybrid Search Function

```sql
CREATE OR REPLACE FUNCTION hybrid_search(
    query_text TEXT,
    query_embedding VECTOR(768),
    match_user_id UUID,
    match_goal_id UUID DEFAULT NULL,
    match_count INT DEFAULT 20,
    full_text_weight FLOAT DEFAULT 1.0,
    semantic_weight FLOAT DEFAULT 1.0,
    rrf_k INT DEFAULT 60
)
RETURNS TABLE (
    id UUID, content TEXT, content_with_context TEXT,
    metadata JSONB, score FLOAT
)
LANGUAGE sql AS $$
WITH semantic AS (
    SELECT dc.id, dc.content, dc.content_with_context, dc.metadata,
        ROW_NUMBER() OVER (ORDER BY dc.embedding <=> query_embedding) AS rank
    FROM document_chunks dc
    WHERE dc.user_id = match_user_id
      AND (match_goal_id IS NULL OR dc.goal_id = match_goal_id)
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count * 2
),
fulltext AS (
    SELECT dc.id, dc.content, dc.content_with_context, dc.metadata,
        ROW_NUMBER() OVER (
            ORDER BY ts_rank(dc.fts, websearch_to_tsquery('english', query_text)) DESC
        ) AS rank
    FROM document_chunks dc
    WHERE dc.user_id = match_user_id
      AND (match_goal_id IS NULL OR dc.goal_id = match_goal_id)
      AND dc.fts @@ websearch_to_tsquery('english', query_text)
    LIMIT match_count * 2
)
SELECT COALESCE(s.id, f.id), COALESCE(s.content, f.content),
    COALESCE(s.content_with_context, f.content_with_context),
    COALESCE(s.metadata, f.metadata),
    (COALESCE(semantic_weight / (rrf_k + s.rank), 0.0) +
     COALESCE(full_text_weight / (rrf_k + f.rank), 0.0)) AS score
FROM semantic s FULL OUTER JOIN fulltext f ON s.id = f.id
ORDER BY score DESC
LIMIT match_count;
$$;
```

---

## Resource Estimates

| Operation | Time (CPU) | Memory |
|---|---|---|
| Docling parse (10-page PDF) | ~5-15s | ~500MB peak |
| nomic-embed-text load | ~2s (first time) | ~300MB resident |
| Embed 100 chunks | ~3-5s | ~100MB |
| Hybrid search query | ~25-85ms | Negligible |
| Rerank 20 candidates | ~30-50ms | ~100MB |
| **Total per document upload** | **~10-25s** | **~800MB peak** |
| **Total per retrieval query** | **~100-150ms** | **~400MB** |

---

## Processing Pipeline Flow

```
User uploads file → Supabase Storage (raw file)
    → user_resources table (metadata, status='pending')
    → Background task (FastAPI):
        1. Download from Supabase Storage
        2. Parse with Docling → Markdown + LaTeX + tables + figures
        3. Structure-aware chunking with deterministic context prefixes
        4. Embed with nomic-embed-text-v1.5 (batch, local CPU)
        5. Store in document_chunks (pgvector + tsvector)
        6. Update user_resources status='completed'
```

## Integration with Existing Research Pipeline

```
Research Pipeline Stage 3 (EXTRACT) — for each topic:
    1. Generate query from topic + content needs
    2. Embed query with nomic-embed-text (search_query: prefix)
    3. Hybrid search via SQL (vector + full-text, RRF fusion) → top 20
    4. Rerank with ms-marco-MiniLM → top 5-8
    5. Merge with Tavily/Serper web search results
    6. Both feed into the LLM extraction step
```

---

## Future Enhancements (Not Now)

- **LightRAG/GraphRAG**: Phase 3 — cross-document concept linking
- **ColPali**: When GPU inference becomes affordable — visual search
- **Full Contextual Retrieval**: When LLM costs allow per-chunk context generation

---

## Python Dependencies

```
docling>=2.0.0             # Document parsing (MIT)
sentence-transformers>=3.0 # Embedding + reranking models
torch>=2.0                 # PyTorch (CPU version for Render)
langchain-text-splitters   # Chunking utilities
pgvector                   # Python pgvector client
```

For CPU-only Render: `pip install torch --index-url https://download.pytorch.org/whl/cpu` (~200MB vs ~2GB)

---

## Image/Figure Extraction Strategy

### The Vision
When the AI Teacher teaches, it uses the student's own teacher's diagrams — creating instant recognition and exam-aligned content. "For this question, draw this diagram" shows the exact diagram from their teacher's PPT.

### Tool Capabilities

| Tool | PDF Images | PDF Vector Diagrams | PPTX Images | PPTX Shapes/SmartArt | Captions | Classification |
|---|---|---|---|---|---|---|
| **Docling** | Yes (rasterizes figure regions) | Yes (rasterizes) | Partial (embedded only) | No | Yes (proximity-based) | Yes (16 categories via EfficientNet-B0) |
| **PyMuPDF** | Yes (native, original resolution) | Yes (`get_drawings()` + `cluster_drawings()`) | N/A | N/A | No | No |
| **python-pptx** | Yes (embedded pictures) | N/A | Yes | No (shapes only as iteration) | No | No |
| **LibreOffice headless** | N/A | N/A | Full slide render | Yes (renders everything) | No | No |

### Recommended: Three-Track Approach

**Track 1 — Docling for PDFs** (primary):
- Layout analysis detects figure regions, links captions, classifies (flow_chart, bar_chart, etc.)
- `generate_picture_images=True`, `images_scale=2.0` (~144 DPI)
- Built-in VLM descriptions via `PictureDescriptionApiOptions` → point at Pollinations or Ollama
- Docling `DocumentFigureClassifier`: 16 categories (bar_chart, flow_chart, line_chart, chemistry_molecular_structure, etc.)

**Track 2 — python-pptx + LibreOffice for PPTX**:
- python-pptx extracts embedded raster images at original quality
- LibreOffice headless renders full slides to PNG (captures SmartArt, charts, shape-based diagrams)
- Then use Docling or VLM on rendered slides to detect/describe figures

**Track 3 — PyMuPDF as fallback**:
- `page.get_images(full=True)` extracts native image objects at original resolution
- `page.get_drawings()` + `cluster_drawings()` detects and groups vector diagrams, then rasterizes each cluster at high DPI

### VLM for Image Understanding

**Option A — Docling built-in VLM** (recommended):
```python
pipeline_options.do_picture_description = True
pipeline_options.picture_description_options = PictureDescriptionApiOptions(
    url="https://text.pollinations.ai/openai",
    model="openai",
    prompt="Describe this educational diagram. List all labels, relationships, and data values.",
)
```

**Option B — Moondream (local, lightweight)**: 1.86B params, ~1.7GB, runs on CPU. Good for basic descriptions.

**Option C — Qwen2.5-VL via Ollama (local, higher quality)**: 7B params, ~8GB VRAM. Best quality free option.

### Supabase Storage — No Manual Conversion Needed

Key finding: **Supabase Storage has built-in image transformations**:
- Automatic WebP conversion on serve (browser-aware)
- On-the-fly thumbnails: `?width=200&height=200&resize=contain`
- CDN-backed with cache control

Strategy: **Upload original PNG, serve optimized** — no need for manual WebP conversion or thumbnail generation.

### Database Schema for Figures

```sql
CREATE TABLE resource_figures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_id UUID NOT NULL REFERENCES user_resources(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    goal_id UUID NOT NULL REFERENCES learning_goals(id) ON DELETE CASCADE,
    storage_path TEXT NOT NULL,
    source_page INTEGER NOT NULL,
    figure_type TEXT NOT NULL,       -- 'diagram', 'chart', 'equation', 'photo', 'table', 'flow_chart'
    caption TEXT,
    vlm_description TEXT,
    concepts TEXT[] DEFAULT '{}',
    labels TEXT[] DEFAULT '{}',
    width INTEGER,
    height INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_resource_figures_concepts ON resource_figures USING GIN(concepts);
CREATE INDEX idx_resource_figures_goal ON resource_figures(goal_id);
CREATE INDEX idx_resource_figures_search ON resource_figures
    USING GIN (to_tsvector('english', coalesce(caption, '') || ' ' || coalesce(vlm_description, '')));
```

### AI Teacher Integration

```
AI Teacher building lesson on "Free Body Diagrams":
  1. Query: SELECT * FROM resource_figures
            WHERE goal_id = ? AND 'free body diagram' = ANY(concepts)
  2. Found: fig_042.png from teacher's PPT, slide 15
     Caption: "Forces on an inclined plane"
  3. AI Teacher: "Here's the diagram from your class notes:"
     [Shows fig_042.png via Supabase Storage URL with WebP transform]
     "As your teacher showed, there are three forces acting..."
```

### Key Limitations
- **No SVG extraction** — all tools rasterize. Use high DPI (2-3x) for quality.
- **Docling PPTX is weak** — must complement with python-pptx + LibreOffice.
- **VLM quality varies** — Moondream is fast but basic; Qwen2.5-VL is better but heavier.

---

## Sources

- [The Ultimate RAG Blueprint 2025/2026 - LangWatch](https://langwatch.ai/blog/the-ultimate-rag-blueprint-everything-you-need-to-know-about-rag-in-2025-2026)
- [RAG vs. GraphRAG: Systematic Evaluation - arXiv](https://arxiv.org/abs/2502.11371)
- [ColPali: Efficient Document Retrieval with VLMs - HuggingFace](https://huggingface.co/blog/manu/colpali)
- [LightRAG GitHub - HKUDS](https://github.com/HKUDS/LightRAG)
- [Hybrid Search RAG - Towards AI](https://pub.towardsai.net/hybrid-search-rag-that-actually-works-bm25-vectors-reranking-in-python-0c02ade0799d)
- [Contextual Retrieval - Anthropic](https://www.anthropic.com/news/contextual-retrieval)
- [Docling GitHub - IBM](https://github.com/docling-project/docling)
- [Supabase pgvector Docs](https://supabase.com/docs/guides/database/extensions/pgvector)
- [Supabase Hybrid Search Docs](https://supabase.com/docs/guides/ai/hybrid-search)
- [Nomic Embed v1.5 - HuggingFace](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5)
- [Docling Figure Export Example](https://docling-project.github.io/docling/examples/export_figures/)
- [Docling Picture Description with VLM](https://docling-project.github.io/docling/examples/pictures_description/)
- [Docling Picture Description with Remote VLM](https://docling-project.github.io/docling/examples/pictures_description_api/)
- [DocumentFigureClassifier - HuggingFace](https://huggingface.co/docling-project/DocumentFigureClassifier)
- [PyMuPDF Vector Graphics](https://artifex.com/blog/extracting-and-creating-vector-graphics-in-a-pdf-using-python-pymupdf)
- [Supabase Storage Image Transformations](https://supabase.com/docs/guides/storage/serving/image-transformations)
- [Moondream GitHub](https://github.com/vikhyat/moondream)
