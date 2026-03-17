"""
Standalone test for the Research Agent v2 pipeline.
Seeds test data into Supabase, runs the 5-stage pipeline, and prints progress.
"""
import asyncio
import os
import sys
import time
import threading
from dotenv import load_dotenv

# Fix Windows console Unicode output
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

TEST_USER_EMAIL = "test-pipeline@pedagora.dev"
TEST_TOPIC = "I want to learn video generation using Diffusion models"


def seed_test_data():
    """Create a test user, goal, preferences, and agent task."""
    users = sb.auth.admin.list_users()
    test_user = None
    for u in users:
        if getattr(u, "email", None) == TEST_USER_EMAIL:
            test_user = u
            break

    if not test_user:
        test_user = sb.auth.admin.create_user(
            {"email": TEST_USER_EMAIL, "password": "test12345678", "email_confirm": True}
        )

    user_id = test_user.id if hasattr(test_user, "id") else test_user.user.id

    profile = sb.table("profiles").select("id").eq("id", user_id).execute()
    if not profile.data:
        sb.table("profiles").insert({
            "id": user_id, "email": TEST_USER_EMAIL,
            "education_level": "undergraduate", "onboarding_status": "completed",
        }).execute()
    else:
        sb.table("profiles").update({"education_level": "undergraduate"}).eq("id", user_id).execute()

    sb.table("user_preferences").upsert({
        "user_id": user_id, "learning_style": "visual", "content_depth": "deep_dive",
        "teaching_style": "example_based", "assessment_type": "project",
        "session_frequency": "three_per_week", "session_duration_minutes": 60, "hours_per_week": 10,
    }, on_conflict="user_id").execute()

    sb.table("learning_goals").insert({
        "user_id": user_id, "title": TEST_TOPIC,
        "end_goal": "Be able to generate short video clips using diffusion models",
        "motivation": "Interested in generative AI and video synthesis", "is_exam_prep": False,
    }).execute()

    goal_result = (
        sb.table("learning_goals").select("id").eq("user_id", user_id)
        .eq("title", TEST_TOPIC).order("created_at", desc=True).limit(1).execute()
    )
    goal_id = goal_result.data[0]["id"]

    sb.table("prerequisites").insert([
        {"goal_id": goal_id, "user_id": user_id, "skill_name": "Python programming", "confidence_level": "advanced"},
        {"goal_id": goal_id, "user_id": user_id, "skill_name": "Linear algebra", "confidence_level": "intermediate"},
        {"goal_id": goal_id, "user_id": user_id, "skill_name": "Neural networks basics", "confidence_level": "intermediate"},
        {"goal_id": goal_id, "user_id": user_id, "skill_name": "Diffusion models theory", "confidence_level": "none"},
    ]).execute()

    sb.table("agent_tasks").insert({
        "goal_id": goal_id, "user_id": user_id, "agent_type": "research", "status": "queued",
    }).execute()

    task_result = (
        sb.table("agent_tasks").select("id").eq("goal_id", goal_id)
        .eq("agent_type", "research").limit(1).execute()
    )
    task_id = task_result.data[0]["id"]

    print(f"  User ID:  {user_id}")
    print(f"  Goal ID:  {goal_id}")
    print(f"  Task ID:  {task_id}")
    print(f"  Topic:    {TEST_TOPIC}")
    return goal_id, user_id, task_id


def monitor_progress(goal_id: str, stop_event: threading.Event):
    """Poll agent_tasks every 3s and print progress."""
    last_msg = ""
    while not stop_event.is_set():
        try:
            task = (
                sb.table("agent_tasks")
                .select("status, progress_percentage, current_task, focus, error_message")
                .eq("goal_id", goal_id).eq("agent_type", "research").single().execute()
            )
            t = task.data
            progress = float(t["progress_percentage"])
            filled = int(30 * progress / 100)
            bar = "#" * filled + "-" * (30 - filled)

            msg = f"  [{bar}] {progress:5.1f}%  |  {t['status']:>9}  |  {t.get('current_task') or ''}"
            if t.get("focus"):
                msg += f"  (focus: {t['focus']})"

            if msg != last_msg:
                print(msg)
                last_msg = msg

            if t["status"] in ("completed", "failed"):
                if t.get("error_message"):
                    print(f"\n  ERROR: {t['error_message']}")
                break
        except Exception:
            pass

        stop_event.wait(3)


def print_results(goal_id: str):
    """Print the final research results including v2 data."""
    sources = sb.table("research_sources").select("*").eq("goal_id", goal_id).execute()
    print(f"\n{'='*70}")
    print(f"  RESEARCH SOURCES: {len(sources.data)} found")
    print(f"{'='*70}")

    by_topic = {}
    total_formulas = 0
    total_code = 0
    total_numerical = 0
    for s in sources.data:
        by_topic.setdefault(s.get("topic_group", "unknown"), []).append(s)

    for topic, topic_sources in by_topic.items():
        print(f"\n  --- {topic} ({len(topic_sources)} sources) ---")
        for s in topic_sources:
            print(f"    [{s['source_type']}] {s['title']}")
            print(f"      URL: {s.get('url', 'N/A')}")
            print(f"      Relevance: {s.get('relevance_score', 0)}  Credibility: {s.get('credibility_score', 0)}")
            if s.get("difficulty_level"):
                print(f"      Difficulty: {s['difficulty_level']}")
            if s.get("key_concepts"):
                print(f"      Concepts: {', '.join(s['key_concepts'][:5])}")

            # v2: Extracted content
            extracted = s.get("extracted_content", {})
            if extracted and extracted.get("detailed_summary"):
                print(f"      Summary: {extracted['detailed_summary'][:200]}...")

            # v2: Formulas
            formulas = s.get("formulas", [])
            if formulas:
                total_formulas += len(formulas)
                print(f"      Formulas ({len(formulas)}):")
                for f in formulas[:3]:
                    print(f"        - {f.get('description', 'N/A')}: {f.get('plain_text', '')[:80]}")

            # v2: Code snippets
            code = s.get("code_snippets", [])
            if code:
                total_code += len(code)
                print(f"      Code snippets ({len(code)}):")
                for c in code[:2]:
                    print(f"        - [{c.get('language', '?')}] {c.get('description', '')[:60]}")

            # v2: Numerical examples
            numerical = s.get("numerical_examples", [])
            if numerical:
                total_numerical += len(numerical)
                print(f"      Numerical examples ({len(numerical)}):")
                for n in numerical[:2]:
                    print(f"        - {n.get('description', '')[:80]}")

    print(f"\n  TOTALS: {total_formulas} formulas, {total_code} code snippets, {total_numerical} numerical examples")

    results = sb.table("research_results").select("*").eq("goal_id", goal_id).execute()
    if results.data:
        r = results.data[0]
        synthesis = r.get("synthesis", {})
        print(f"\n{'='*70}")
        print(f"  SYNTHESIS (v{r.get('version', 1)})")
        print(f"{'='*70}")
        print(f"\n  Summary: {synthesis.get('overall_summary', 'N/A')}")
        print(f"  Difficulty: {synthesis.get('estimated_difficulty', 'N/A')}")
        print(f"  Total sources: {synthesis.get('total_sources', 0)}")

        if synthesis.get("recommended_learning_path"):
            print(f"\n  Recommended Learning Path:")
            for step in synthesis["recommended_learning_path"]:
                hours = f" (~{step.get('estimated_hours', '?')}h)" if step.get("estimated_hours") else ""
                print(f"    {step.get('order', '?')}. {step.get('topic', '')}{hours} -- {step.get('reason', '')}")

        if synthesis.get("key_themes"):
            print(f"\n  Key Themes: {', '.join(synthesis['key_themes'])}")

        if synthesis.get("gaps_identified"):
            print(f"\n  Gaps:")
            for gap in synthesis["gaps_identified"]:
                severity = gap.get("severity", "minor")
                print(f"    - [{severity.upper()}] {gap.get('topic', '')}: {gap.get('description', '')}")
                if gap.get("missing_content_type"):
                    print(f"      Missing: {gap['missing_content_type']}")

        # v2: Teaching notes
        teaching_notes = r.get("teaching_notes", {})
        if teaching_notes:
            print(f"\n  Teaching Notes ({len(teaching_notes)} topics):")
            for topic, notes in list(teaching_notes.items())[:5]:
                print(f"    {topic}: {notes[:120]}...")

        # v2: Cross-topic formulas
        cross_formulas = r.get("cross_topic_formulas", [])
        if cross_formulas:
            print(f"\n  Cross-Topic Formulas ({len(cross_formulas)}):")
            for f in cross_formulas[:5]:
                print(f"    - {f.get('description', 'N/A')}: {f.get('plain_text', '')[:80]}")

        # v2: Demo codebases
        demo_codebases = r.get("demo_codebases", [])
        if demo_codebases:
            print(f"\n  Demo Codebases ({len(demo_codebases)}):")
            for cb in demo_codebases:
                print(f"    - {cb.get('repo_name', 'N/A')} ({cb.get('stars', 0)} stars)")
                print(f"      Suitability: {cb.get('suitability_score', 0)}")
                if cb.get("setup_instructions"):
                    print(f"      Setup: {cb['setup_instructions'][:100]}")

        # v2: Coding exercises
        exercises = r.get("coding_exercises", [])
        if exercises:
            print(f"\n  Coding Exercises ({len(exercises)}):")
            for ex in exercises:
                print(f"    - [{ex.get('difficulty', '?')}] {ex.get('title', 'N/A')}")
                if ex.get("description"):
                    print(f"      {ex['description'][:100]}")

    task = (
        sb.table("agent_tasks").select("logs")
        .eq("goal_id", goal_id).eq("agent_type", "research").single().execute()
    )
    logs = task.data.get("logs", [])
    if logs:
        print(f"\n{'='*70}")
        print(f"  AGENT LOGS ({len(logs)} entries)")
        print(f"{'='*70}")
        for log in logs:
            level = log.get("level", "info").upper()
            print(f"  [{level:>7}] {log.get('message', '')}")


async def run_pipeline(goal_id: str, user_id: str):
    from app.agents.pipeline import run_research_pipeline
    await run_research_pipeline(goal_id, user_id)


def main():
    print("\n" + "=" * 70)
    print("  PEDAGORA RESEARCH AGENT v2.1 -- TEST RUN")
    print(f"  Decompose: {os.environ.get('DECOMPOSE_MODEL', 'google-gla:gemini-2.5-flash')}")
    print(f"  Extract:   {os.environ.get('EXTRACT_MODEL', 'groq:qwen/qwen3-32b')}")
    print(f"  Synthesize:{os.environ.get('SYNTHESIZE_MODEL', 'google-gla:gemini-2.5-flash')}")
    print("=" * 70)

    print("\n[1/3] Seeding test data...")
    goal_id, user_id, task_id = seed_test_data()

    print("\n[2/3] Running 5-stage pipeline...\n")
    stop_event = threading.Event()
    monitor = threading.Thread(target=monitor_progress, args=(goal_id, stop_event), daemon=True)
    monitor.start()

    start = time.time()
    try:
        asyncio.run(run_pipeline(goal_id, user_id))
    except Exception as e:
        print(f"\n  PIPELINE ERROR: {e}")
    finally:
        stop_event.set()
        monitor.join(timeout=5)

    elapsed = time.time() - start
    print(f"\n  Pipeline completed in {elapsed:.1f}s")

    print("\n[3/3] Results...")
    print_results(goal_id)

    print(f"\n  Goal ID kept in Supabase: {goal_id}")


if __name__ == "__main__":
    main()
