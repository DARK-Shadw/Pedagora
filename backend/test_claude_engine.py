"""
Test Claude Code Engine — run this directly to see real-time logs.

Usage:
  cd backend
  python test_claude_engine.py
"""

import asyncio
import json
import logging
import os
import subprocess
import shutil
import sys
import tempfile
import time


def find_claude():
    """Find claude binary."""
    path = shutil.which("claude")
    if path:
        return path
    # Windows fallback
    home = os.path.expanduser("~")
    local = os.path.join(home, ".local", "bin", "claude")
    if os.path.exists(local):
        return local
    raise RuntimeError("Claude CLI not found")


def test_sync_basic():
    """Test 1: Basic sync subprocess — see raw output."""
    print("\n" + "=" * 60)
    print("TEST 1: Basic sync subprocess (should take ~10-30s)")
    print("=" * 60)

    claude_path = find_claude()
    print(f"Claude binary: {claude_path}")

    # Build env
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    env.pop("ANTHROPIC_API_KEY", None)
    env["ENABLE_TOOL_SEARCH"] = "false"

    cmd = [
        claude_path,
        "--print",
        "--model", "sonnet",
        "--permission-mode", "bypassPermissions",
        "--no-session-persistence",
        "--disallowedTools", "MCPSearch,ToolSearch",
        "--output-format", "json",
    ]

    prompt = 'Say "Hello from Claude Code Engine" in exactly those words. Nothing else.'

    print(f"Command: {' '.join(cmd[:6])}...")
    print(f"Prompt: {prompt}")
    print(f"Starting at {time.strftime('%H:%M:%S')}...")

    start = time.time()
    result = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )

    elapsed = time.time() - start
    print(f"Exit code: {result.returncode} ({elapsed:.1f}s)")

    if result.stdout:
        try:
            data = json.loads(result.stdout)
            print(f"Result: {data.get('result', '')[:200]}")
            print(f"Cost: ${data.get('total_cost_usd', 0):.4f}")
            print(f"Tokens: {data.get('usage', {}).get('input_tokens', 0)} in, {data.get('usage', {}).get('output_tokens', 0)} out")
        except json.JSONDecodeError:
            print(f"Raw stdout: {result.stdout[:500]}")

    if result.stderr:
        print(f"Stderr: {result.stderr[:500]}")

    print(f"TEST 1: {'PASS' if result.returncode == 0 else 'FAIL'}")
    return result.returncode == 0


def test_sync_websearch():
    """Test 2: WebSearch tool — see how long it takes."""
    print("\n" + "=" * 60)
    print("TEST 2: WebSearch (should take ~30-90s)")
    print("=" * 60)

    claude_path = find_claude()
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    env.pop("ANTHROPIC_API_KEY", None)
    env["ENABLE_TOOL_SEARCH"] = "false"

    cmd = [
        claude_path,
        "--print",
        "--model", "sonnet",
        "--permission-mode", "bypassPermissions",
        "--no-session-persistence",
        "--disallowedTools", "MCPSearch,ToolSearch",
        "--allowedTools", "WebSearch,WebFetch",
        "--output-format", "json",
        "--max-turns", "5",
    ]

    prompt = """Find 3 sources about "diffusion models tutorial".
Return ONLY valid JSON (no markdown): {"sources": [{"title": "...", "url": "..."}]}"""

    print(f"Prompt: {prompt[:80]}...")
    print(f"Starting at {time.strftime('%H:%M:%S')}...")

    start = time.time()
    result = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )

    elapsed = time.time() - start
    print(f"Exit code: {result.returncode} ({elapsed:.1f}s)")

    if result.stdout:
        try:
            data = json.loads(result.stdout)
            result_text = data.get("result", "")
            print(f"Cost: ${data.get('total_cost_usd', 0):.4f}")

            # Try to parse the inner JSON
            stripped = result_text.strip()
            if stripped.startswith("```"):
                lines = stripped.split("\n")
                if lines[-1].strip() == "```":
                    lines = lines[1:-1]
                else:
                    lines = lines[1:]
                stripped = "\n".join(lines)

            try:
                inner = json.loads(stripped)
                sources = inner.get("sources", [])
                print(f"Sources found: {len(sources)}")
                for s in sources:
                    print(f"  - {s.get('title', '?')[:60]}")
                    print(f"    {s.get('url', '?')[:60]}")
            except json.JSONDecodeError:
                print(f"Result text: {result_text[:300]}")
        except json.JSONDecodeError:
            print(f"Raw stdout: {result.stdout[:500]}")

    if result.stderr:
        print(f"Stderr: {result.stderr[:300]}")

    print(f"TEST 2: {'PASS' if result.returncode == 0 else 'FAIL'}")
    return result.returncode == 0


def test_streaming():
    """Test 3: Stream JSON mode — see events in real-time."""
    print("\n" + "=" * 60)
    print("TEST 3: Streaming mode (real-time events)")
    print("=" * 60)

    claude_path = find_claude()
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    env.pop("ANTHROPIC_API_KEY", None)
    env["ENABLE_TOOL_SEARCH"] = "false"

    cmd = [
        claude_path,
        "--print",
        "--model", "haiku",
        "--permission-mode", "bypassPermissions",
        "--no-session-persistence",
        "--disallowedTools", "MCPSearch,ToolSearch",
        "--allowedTools", "WebSearch",
        "--output-format", "stream-json",
        "--verbose",
        "--max-turns", "3",
    ]

    prompt = 'Search for "DDPM diffusion models" and return the top 2 results as JSON: {"results": [{"title": "...", "url": "..."}]}'

    # Write prompt to file (avoids stdin issues)
    prompt_file = os.path.join(tempfile.gettempdir(), "test_prompt.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)

    print(f"Prompt: {prompt[:80]}...")
    print(f"Starting at {time.strftime('%H:%M:%S')}...")
    print("--- LIVE EVENTS ---")

    start = time.time()
    with open(prompt_file, "r", encoding="utf-8") as stdin_file:
        process = subprocess.Popen(
            cmd,
            stdin=stdin_file,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=False,
            bufsize=0,
        )

    tool_calls = 0
    text_chunks = 0
    final_result = ""

    try:
        for line in iter(process.stdout.readline, b""):
            if not line:
                break

            elapsed = time.time() - start
            line_text = line.decode("utf-8", errors="ignore").strip()
            if not line_text:
                continue

            try:
                data = json.loads(line_text)
                msg_type = data.get("type")

                if msg_type == "assistant":
                    message = data.get("message", {})
                    for block in message.get("content", []):
                        if block.get("type") == "text" and block.get("text"):
                            text_chunks += 1
                            text = block["text"]
                            if len(text) > 80:
                                print(f"  [{elapsed:5.1f}s] TEXT: {text[:80]}...")
                            else:
                                print(f"  [{elapsed:5.1f}s] TEXT: {text}")
                        elif block.get("type") == "tool_use":
                            tool_calls += 1
                            print(f"  [{elapsed:5.1f}s] TOOL: {block.get('name', '?')} -> {json.dumps(block.get('input', {}))[:80]}")

                elif msg_type == "result":
                    final_result = data.get("result", "")
                    cost = data.get("total_cost_usd", 0)
                    print(f"  [{elapsed:5.1f}s] RESULT: cost=${cost:.4f}")

            except json.JSONDecodeError:
                print(f"  [{elapsed:5.1f}s] RAW: {line_text[:100]}")

        process.wait()
    except KeyboardInterrupt:
        process.kill()
        print("\nInterrupted by user")

    elapsed = time.time() - start
    print(f"--- END ({elapsed:.1f}s) ---")
    print(f"Tool calls: {tool_calls}, Text chunks: {text_chunks}")
    print(f"Final result: {final_result[:200]}")

    # Cleanup
    os.remove(prompt_file)

    print(f"TEST 3: {'PASS' if process.returncode == 0 else 'FAIL'}")
    return process.returncode == 0


def test_full_research():
    """Test 4: Full research v3 pipeline with live progress."""
    print("\n" + "=" * 60)
    print("TEST 4: Full Research v3 (production, live progress)")
    print("=" * 60)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from app.services.supabase import get_supabase
    from app.agents.research_v3 import run_research_v3

    sb = get_supabase()
    goal_id = "25b76657-1bd7-49d6-8537-ee6133902527"
    user_id = "d55e1541-4bf6-4ba9-8d98-f25bd74e78db"

    # Reset
    sb.table("agent_tasks").update({
        "status": "queued", "progress_percentage": 0,
        "current_task": None, "error_message": None,
    }).eq("goal_id", goal_id).eq("agent_type", "research").execute()
    sb.table("research_sources").delete().eq("goal_id", goal_id).execute()
    sb.table("research_results").delete().eq("goal_id", goal_id).execute()
    print("DB reset, starting research...\n")

    async def run():
        start = time.time()
        result = await run_research_v3(goal_id, user_id)
        elapsed = time.time() - start

        topics = result.get("topic_tree", {}).get("topic_groups", [])
        sources = result.get("sources", [])
        synthesis = result.get("synthesis", {})
        prereqs = [t for t in topics if t.get("priority") == "prerequisite"]
        formulas = sum(len(s.get("formulas", [])) for s in sources)
        visuals = sum(1 for s in sources if s.get("visual_opportunity"))

        print(f"\n{'='*60}")
        print(f"RESEARCH COMPLETE — {elapsed:.0f}s ({elapsed/60:.1f} min)")
        print(f"{'='*60}")
        print(f"Topics: {len(topics)} ({len(prereqs)} prerequisite)")
        for t in topics:
            print(f"  [{t.get('priority')}] {t.get('topic_name')}")
        print(f"\nSources: {len(sources)}")
        for s in sources:
            print(f"  [{s.get('source_type','?')}] {s.get('title','?')[:65]}")
        print(f"\nFormulas: {formulas}, Visuals: {visuals}")
        print(f"Gaps: {len(synthesis.get('gaps', []))}")
        print(f"Exercises: {len(synthesis.get('coding_exercises', []))}")
        print(f"SAVED TO DB")
        return True

    try:
        return asyncio.run(run())
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Claude Code Engine — Diagnostic Tests")
    print(f"Python: {sys.version}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = []

    # Test 1: Basic
    try:
        results.append(("Basic", test_sync_basic()))
    except Exception as e:
        print(f"TEST 1 EXCEPTION: {e}")
        results.append(("Basic", False))

    # Test 2: WebSearch
    try:
        results.append(("WebSearch", test_sync_websearch()))
    except Exception as e:
        print(f"TEST 2 EXCEPTION: {e}")
        results.append(("WebSearch", False))

    # Test 3: Streaming
    try:
        results.append(("Streaming", test_streaming()))
    except Exception as e:
        print(f"TEST 3 EXCEPTION: {e}")
        results.append(("Streaming", False))

    # Test 4: Full research (optional — pass --full flag)
    if "--full" in sys.argv:
        try:
            results.append(("Full Research", test_full_research()))
        except Exception as e:
            print(f"TEST 4 EXCEPTION: {e}")
            results.append(("Full Research", False))
    else:
        print("\nSkipping Test 4 (full research). Run with --full to include it.")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        print(f"  {name}: {'PASS' if passed else 'FAIL'}")
