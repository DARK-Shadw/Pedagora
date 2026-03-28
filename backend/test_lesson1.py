"""Generate lesson 1 storyboard only (reuse existing structure). Saves to DB."""
import asyncio, json, logging, sys, time
logging.basicConfig(level=logging.INFO, format="%(message)s")
sys.stdout.reconfigure(encoding="utf-8")

async def main():
    from app.engine.claude_engine import ClaudeEngine
    from app.services.supabase import get_supabase
    from app.agents.course_planner.pipeline_v4 import _build_research_context, _build_lesson_research
    from app.agents.course_planner.prompts_v4 import LESSON_STORYBOARD_SYSTEM, LESSON_STORYBOARD_PROMPT
    from app.services.agent_task import fetch_research_results, fetch_research_sources

    sb = get_supabase()
    engine = ClaudeEngine(model="sonnet")
    goal_id = "25b76657-1bd7-49d6-8537-ee6133902527"

    # Reuse existing course structure — don't regenerate
    cp = sb.table("course_plans").select("course_structure, lesson_plans").eq("goal_id", goal_id).execute()
    if not cp.data:
        print("No course plan. Run planner first."); return

    structure = cp.data[0].get("course_structure", {})
    existing_plans = cp.data[0].get("lesson_plans", {})

    # Get first lesson
    first = None
    for mod in structure.get("modules", []):
        for les in mod.get("lessons", []):
            first = les; break
        if first: break
    if not first:
        print("No lessons found."); return

    lesson_id = first["lesson_id"]
    print(f"Lesson 1: {first['title']}")
    print(f"Objectives: {first.get('learning_objectives', [])}")

    # Get research data
    research_results = await fetch_research_results(goal_id)
    research_sources = await fetch_research_sources(goal_id)
    research_ctx = _build_research_context(research_results, research_sources)
    lesson_research = _build_lesson_research(first.get("topics_covered", []), research_sources, research_ctx["synthesis"])

    # Get student name
    student_name = "Aswin"
    try:
        prof = sb.table("profiles").select("name,email").eq("id", "d55e1541-4bf6-4ba9-8d98-f25bd74e78db").single().execute()
        if prof.data: student_name = prof.data.get("name") or prof.data.get("email", "").split("@")[0]
    except: pass

    prompt = LESSON_STORYBOARD_PROMPT.format(
        lesson_title=first["title"], lesson_type=first.get("lesson_type", "theory"),
        estimated_minutes=first.get("estimated_minutes", 30),
        objectives=", ".join(first.get("learning_objectives", [])),
        topics=", ".join(first.get("topics_covered", [])),
        education_level="graduate", learning_style="visual", student_name=student_name,
        key_concepts=lesson_research["key_concepts"],
        visual_opportunities=lesson_research["visual_opportunities"],
    )

    print(f"\nGenerating storyboard ({len(prompt)} chars prompt)...")
    start = time.time()

    result = await engine.run(prompt=prompt, system_prompt=LESSON_STORYBOARD_SYSTEM, timeout=600)

    elapsed = time.time() - start
    storyboard = json.loads(result["result"])
    frames = storyboard.get("frames", [])
    total_secs = sum(f.get("estimated_seconds", 0) for f in frames)
    interactions = sum(1 for f in frames if f.get("interaction"))

    print(f"\nDone in {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"Frames: {len(frames)} | Duration: {total_secs//60}:{total_secs%60:02d} | Interactions: {interactions}")
    print(f"Hook: {storyboard.get('opening_hook', '?')[:80]}")
    print()

    cum = 0
    for f in frames:
        secs = f.get("estimated_seconds", 0); cum += secs
        phase = f.get("story_phase", "?"); vtype = f.get("visual_type", "?")
        narr = f.get("narration_spoken", "")[:80]
        inter = " [Q]" if f.get("interaction") else ""
        print(f"[{cum//60}:{cum%60:02d}] [{phase:10}] {vtype:12} {narr}...{inter}")

    # Save to DB
    existing_plans[lesson_id] = {
        "lesson_id": lesson_id, "title": first["title"],
        "opening_hook": storyboard.get("opening_hook", ""),
        "frames": frames, "total_frames": len(frames),
        "total_interactions": interactions,
    }
    sb.table("course_plans").update({"lesson_plans": existing_plans}).eq("goal_id", goal_id).execute()
    print(f"\nSAVED TO DB")

if __name__ == "__main__":
    asyncio.run(main())
