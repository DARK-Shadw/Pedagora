"""Export the diffusion course chapter 1: syllabus + Groq dialogues + animation paths.

Pulls course_plan from Supabase for goal 25b76657, dumps the course structure
(syllabus), the lesson 1 plan, calls Groq Llama 3.3 70B to generate per-frame
teacher dialogue (the same speech the live classroom would generate), and writes
a markdown index linking everything to the rendered HTML animations on disk.
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
sys.stdout.reconfigure(encoding="utf-8")

GOAL_ID = "25b76657-1bd7-49d6-8537-ee6133902527"
LESSON_ID = "mod1-les1"
TEACHING_STYLE = "lecture"
STUDENT_NAME = "Aswin"

OUT_DIR = Path(__file__).parent / "diffusion_chapter_export"
VISUALS_DIR = Path(__file__).parent / "generated_visuals"


async def main():
    from app.services.supabase import get_supabase
    from app.agents.teacher.speech_gen import (
        generate_frame_speeches,
        generate_step_speeches,
    )

    OUT_DIR.mkdir(exist_ok=True)
    sb = get_supabase()

    # ─── 1. Pull course_plans row ───
    print("[1/4] Fetching course_plan from Supabase...")
    cp = (
        sb.table("course_plans")
        .select("course_structure, lesson_plans, generation_metadata")
        .eq("goal_id", GOAL_ID)
        .execute()
    )
    if not cp.data:
        print(f"ERROR: No course_plan found for goal {GOAL_ID}")
        return

    row = cp.data[0]
    structure = row.get("course_structure") or {}
    lesson_plans = row.get("lesson_plans") or {}

    # Save raw structure JSON
    (OUT_DIR / "course_structure.json").write_text(
        json.dumps(structure, indent=2), encoding="utf-8"
    )
    print(f"  saved course_structure.json")

    # Build readable syllabus markdown
    syll = ["# Diffusion Course — Syllabus\n"]
    syll.append(f"**Title:** {structure.get('course_title', '?')}\n")
    syll.append(f"**Description:** {structure.get('course_description', '')}\n")
    syll.append(f"**Total minutes:** {structure.get('total_estimated_minutes', '?')}\n")
    syll.append(f"**Difficulty:** {structure.get('difficulty_progression', '?')}\n\n")
    for mod in structure.get("modules", []):
        syll.append(f"## {mod.get('module_id', '?')} — {mod.get('title', '?')}")
        syll.append(f"_{mod.get('description', '')}_\n")
        syll.append(f"Estimated: {mod.get('estimated_minutes', '?')} min\n")
        for les in mod.get("lessons", []):
            syll.append(f"### {les.get('lesson_id', '?')} — {les.get('title', '?')}")
            syll.append(f"- **Type:** {les.get('lesson_type', 'theory')}")
            syll.append(f"- **Minutes:** {les.get('estimated_minutes', '?')}")
            objs = les.get("learning_objectives", [])
            if objs:
                syll.append(f"- **Objectives:**")
                for o in objs:
                    syll.append(f"  - {o}")
            topics = les.get("topics_covered", [])
            if topics:
                syll.append(f"- **Topics:** {', '.join(topics)}")
            prereqs = les.get("prerequisites", [])
            if prereqs:
                syll.append(f"- **Prereqs:** {', '.join(prereqs)}")
            syll.append("")
    (OUT_DIR / "syllabus.md").write_text("\n".join(syll), encoding="utf-8")
    print(f"  saved syllabus.md")

    # ─── 2. Pull lesson 1 plan ───
    print("\n[2/4] Extracting lesson 1 plan...")
    lesson = lesson_plans.get(LESSON_ID)
    if not lesson:
        print(f"ERROR: lesson {LESSON_ID} not in lesson_plans. Available: {list(lesson_plans.keys())}")
        return

    (OUT_DIR / "lesson1_plan.json").write_text(
        json.dumps(lesson, indent=2), encoding="utf-8"
    )
    frames = lesson.get("frames", [])
    print(f"  saved lesson1_plan.json ({len(frames)} frames, opening_hook present={bool(lesson.get('opening_hook'))})")

    # ─── 3. Generate Groq dialogues per frame ───
    print(f"\n[3/4] Generating Groq dialogues for {len(frames)} frames...")
    recent_context: list[dict] = []
    dialogues: list[dict] = []

    for i, frame in enumerate(frames):
        fid = frame.get("frame_id", f"f{i+1:02d}")
        vtype = frame.get("visual_type", "animation")
        vspec = frame.get("visual_spec", {}) or {}
        description = (
            vspec.get("description")
            or frame.get("narration", "")
            or str(vspec)[:300]
        )
        steps = frame.get("steps") or []

        print(f"  [{i+1}/{len(frames)}] {fid} ({vtype}) — {len(steps)} steps")

        entry: dict = {
            "frame_id": fid,
            "visual_type": vtype,
            "story_phase": frame.get("story_phase", ""),
            "estimated_seconds": frame.get("estimated_seconds", 0),
            "narration_planned": frame.get("narration_spoken", ""),
        }

        try:
            if steps:
                step_labels = [s.get("label") or s.get("step_id") or f"step-{j+1}" for j, s in enumerate(steps)]
                speeches = await generate_step_speeches(
                    frame=frame,
                    step_labels=step_labels,
                    student_name=STUDENT_NAME,
                    teaching_style=TEACHING_STYLE,
                )
                entry["mode"] = "step_speeches"
                entry["steps"] = [
                    {
                        "step_id": s.get("step_id", f"step-{j+1}"),
                        "label": s.get("label", ""),
                        "description": s.get("description", ""),
                        "groq_speech": speeches[j] if j < len(speeches) else "",
                    }
                    for j, s in enumerate(steps)
                ]
                joined = " ".join(speeches)
            else:
                chunks = await generate_frame_speeches(
                    description=str(description),
                    visual_type=vtype,
                    frame_index=i,
                    total_frames=len(frames),
                    student_name=STUDENT_NAME,
                    recent_context=recent_context,
                    teaching_style=TEACHING_STYLE,
                    estimated_seconds=int(frame.get("estimated_seconds", 30)),
                )
                entry["mode"] = "frame_speeches"
                entry["chunks"] = chunks
                joined = " ".join(chunks)

            entry["status"] = "ok"
            recent_context.append({"role": "teacher", "content": joined[:200]})
            recent_context = recent_context[-6:]
        except Exception as e:
            entry["status"] = "error"
            entry["error"] = str(e)
            print(f"    ERROR: {e}")

        dialogues.append(entry)

    (OUT_DIR / "teacher_dialogues.json").write_text(
        json.dumps(
            {
                "goal_id": GOAL_ID,
                "lesson_id": LESSON_ID,
                "model": "groq:llama-3.3-70b-versatile",
                "teaching_style": TEACHING_STYLE,
                "student_name": STUDENT_NAME,
                "frame_count": len(frames),
                "dialogues": dialogues,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  saved teacher_dialogues.json ({len(dialogues)} entries)")

    # ─── 4. Map frames to animation HTML files & write index ───
    print("\n[4/4] Mapping frames to animation HTML files...")

    def find_html(frame_id: str) -> Path | None:
        # Try several naming variants
        candidates = [
            VISUALS_DIR / f"{frame_id}.html",
            VISUALS_DIR / f"{frame_id.split('-')[-1]}.html",
        ]
        for c in candidates:
            if c.exists():
                return c
        return None

    index = ["# Diffusion Course — Chapter 1 Export\n"]
    index.append(f"**Goal:** `{GOAL_ID}`")
    index.append(f"**Lesson:** `{LESSON_ID}` — {lesson.get('title', '?')}\n")
    index.append(f"**Opening hook:** {lesson.get('opening_hook', '')}\n")
    index.append("## Files in this export\n")
    index.append("- `course_structure.json` — full Supabase course_structure")
    index.append("- `syllabus.md` — readable syllabus")
    index.append("- `lesson1_plan.json` — full lesson 1 storyboard (frames)")
    index.append("- `teacher_dialogues.json` — Groq Llama 3.3 70B dialogue per frame\n")
    index.append("## Frames + Dialogue + Animation\n")
    index.append("| # | Frame | Type | Phase | Sec | HTML | Dialogue mode |")
    index.append("|---|-------|------|-------|-----|------|---------------|")

    matched = 0
    for i, (frame, dlg) in enumerate(zip(frames, dialogues), start=1):
        fid = frame.get("frame_id", f"f{i:02d}")
        html = find_html(fid)
        if html:
            matched += 1
            html_str = f"`generated_visuals/{html.name}`"
        else:
            html_str = "_(missing)_"
        index.append(
            f"| {i} | `{fid}` | {frame.get('visual_type', '?')} | "
            f"{frame.get('story_phase', '?')} | {frame.get('estimated_seconds', '?')} | "
            f"{html_str} | {dlg.get('mode', '?')} |"
        )
    index.append(f"\n_Matched {matched}/{len(frames)} frames to rendered HTML files._\n")

    index.append("## Per-frame dialogue (Groq output)\n")
    for i, (frame, dlg) in enumerate(zip(frames, dialogues), start=1):
        fid = frame.get("frame_id", f"f{i:02d}")
        index.append(f"### {i}. `{fid}` — {frame.get('visual_type', '?')}\n")
        narr = frame.get("narration_spoken", "").strip()
        if narr:
            index.append(f"_Planned narration (Opus storyboard):_\n\n> {narr}\n")
        if dlg.get("status") != "ok":
            index.append(f"**ERROR:** {dlg.get('error', '?')}\n")
            continue
        if dlg.get("mode") == "step_speeches":
            for s in dlg.get("steps", []):
                index.append(f"- **{s.get('label', '?')}** — {s.get('groq_speech', '')}")
            index.append("")
        else:
            for j, c in enumerate(dlg.get("chunks", []), start=1):
                index.append(f"{j}. {c}")
            index.append("")

    (OUT_DIR / "INDEX.md").write_text("\n".join(index), encoding="utf-8")
    print(f"  saved INDEX.md (matched {matched}/{len(frames)} HTML files)")
    print(f"\nDone. Output: {OUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
