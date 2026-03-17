"""Resource processing pipeline orchestrator.

Downloads files from Supabase Storage, parses with Docling/python-pptx,
chunks relevant sections, embeds chunks, extracts figures with VLM descriptions,
and stores everything in the database.
"""

import logging
import traceback
from pathlib import Path
import tempfile

from app.services.supabase import get_supabase
from app.services.embeddings import embed_texts
from app.config import get_settings

logger = logging.getLogger(__name__)


async def run_resource_pipeline(goal_id: str, user_id: str) -> None:
    """Process all uploaded resources for a goal."""
    sb = get_supabase()
    settings = get_settings()

    # Fetch all resources with status 'processing'
    result = (
        sb.table("user_resources")
        .select("*")
        .eq("goal_id", goal_id)
        .eq("user_id", user_id)
        .eq("status", "processing")
        .execute()
    )

    if not result.data:
        logger.warning(f"No processing resources found for goal {goal_id}")
        return

    for resource in result.data:
        try:
            await _process_single_resource(resource, goal_id, user_id, sb, settings)
        except Exception as e:
            logger.error(f"Failed to process resource {resource['id']}: {traceback.format_exc()}")
            sb.table("user_resources").update({
                "status": "failed",
                "error_message": str(e)[:500],
            }).eq("id", resource["id"]).execute()


async def _process_single_resource(resource: dict, goal_id: str, user_id: str, sb, settings) -> None:
    """Process a single uploaded resource file."""
    resource_id = resource["id"]
    file_name = resource["file_name"]
    file_type = resource["file_type"]
    storage_path = resource["storage_path"]

    logger.info(f"Processing resource: {file_name} ({file_type})")

    # 1. Download file from Supabase Storage to temp dir
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / file_name

        file_bytes = sb.storage.from_("user-resources").download(storage_path)
        tmp_path.write_bytes(file_bytes)

        # 2. Parse document
        from app.resources.parser import parse_document
        parsed = await parse_document(str(tmp_path), file_type)

        # Update resource with TOC and page count
        sb.table("user_resources").update({
            "page_count": parsed.page_count,
            "toc_structure": parsed.toc,
        }).eq("id", resource_id).execute()

        # 3. Chunk parsed sections
        from app.resources.chunker import chunk_sections
        chunks = chunk_sections(parsed.sections, file_name)

        if not chunks:
            logger.warning(f"No chunks produced for {file_name}")
            sb.table("user_resources").update({
                "status": "ready",
                "chunk_count": 0,
                "figure_count": 0,
            }).eq("id", resource_id).execute()
            return

        # 4. Insert sections into database
        if parsed.sections:
            section_records = []
            for section in parsed.sections:
                section_records.append({
                    "resource_id": resource_id,
                    "user_id": user_id,
                    "goal_id": goal_id,
                    "title": section.title,
                    "level": section.level,
                    "path": section.path,
                    "content": section.content[:50000] if section.content else None,
                    "page_start": section.page_start,
                    "page_end": section.page_end,
                    "is_relevant": True,
                })
            sb.table("resource_sections").insert(section_records).execute()

        # 5. Embed chunks in batches
        chunk_texts = [f"{c.context_prefix}\n{c.content}" for c in chunks]
        embeddings = await embed_texts(chunk_texts)

        # 6. Insert chunks with embeddings
        chunk_records = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_records.append({
                "resource_id": resource_id,
                "user_id": user_id,
                "goal_id": goal_id,
                "content": chunk.content,
                "context_prefix": chunk.context_prefix,
                "chunk_index": i,
                "token_count": chunk.token_count,
                "page_number": chunk.page_number,
                "embedding": embedding,
            })

        # Insert in batches of 50 to avoid payload limits
        for batch_start in range(0, len(chunk_records), 50):
            batch = chunk_records[batch_start:batch_start + 50]
            sb.table("resource_chunks").insert(batch).execute()

        # 7. Process figures
        figure_count = 0
        if parsed.figures:
            from app.resources.figures import describe_figure

            for fig in parsed.figures:
                try:
                    description_result = await describe_figure(
                        image_bytes=fig.image_bytes,
                        caption=fig.caption,
                        context=f"From document: {file_name}",
                    )

                    # Upload figure image to storage
                    fig_storage_path = f"{user_id}/{goal_id}/figures/{resource_id}_{figure_count}.png"
                    sb.storage.from_("user-resources").upload(
                        fig_storage_path,
                        fig.image_bytes,
                        {"content-type": "image/png"},
                    )

                    # Embed the description for search
                    desc_embedding = await embed_texts([description_result.description])

                    sb.table("resource_figures").insert({
                        "resource_id": resource_id,
                        "user_id": user_id,
                        "goal_id": goal_id,
                        "storage_path": fig_storage_path,
                        "page_number": fig.page_number,
                        "caption": fig.caption,
                        "figure_type": description_result.figure_type,
                        "description": description_result.description,
                        "concepts": description_result.concepts,
                        "description_embedding": desc_embedding[0] if desc_embedding else None,
                    }).execute()

                    figure_count += 1
                except Exception as e:
                    logger.warning(f"Failed to process figure from {file_name}: {e}")

        # 8. Update resource as ready
        sb.table("user_resources").update({
            "status": "ready",
            "chunk_count": len(chunks),
            "figure_count": figure_count,
            "processed_at": "now()",
        }).eq("id", resource_id).execute()

        logger.info(
            f"Resource {file_name} processed: {len(chunks)} chunks, {figure_count} figures"
        )
