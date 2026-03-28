"""
ClaudeEngine — Python wrapper for Claude Code CLI.

Uses subprocess.Popen with file-based stdin and line-by-line stdout reading.
Matches the proven pattern from FlowBuilder's claude_code_runner.py.
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=10)


class ClaudeEngine:
    """Wraps Claude Code CLI for programmatic use."""

    def __init__(self, model: str = "sonnet"):
        self.model = model
        self.claude_path = self._find_claude_path()
        logger.info(f"[ClaudeEngine] Initialized: claude={self.claude_path}, model={model}")

    def _find_claude_path(self) -> str:
        if os.name == "nt":
            path = shutil.which("claude")
            if path:
                return path
            user_local = Path.home() / ".local" / "bin" / "claude"
            if user_local.exists():
                return str(user_local)
        else:
            for p in [Path.home() / ".local" / "bin" / "claude", Path("/usr/local/bin/claude")]:
                if p.exists():
                    return str(p)
            path = shutil.which("claude")
            if path:
                return path
        raise RuntimeError("Claude Code CLI not found")

    def _build_env(self) -> dict:
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)
        env.pop("ANTHROPIC_API_KEY", None)
        env["ENABLE_TOOL_SEARCH"] = "false"
        return env

    def _run_sync(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_turns: int | None = None,
        timeout: int = 600,
        cwd: str | None = None,
    ) -> dict:
        """Run Claude Code synchronously using Popen + file stdin (proven pattern)."""
        execution_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        # Write prompt to temp file
        prompt_file = Path(tempfile.gettempdir()) / f"pedagora_prompt_{execution_id}.txt"
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n---\n\n{prompt}"
        prompt_file.write_text(full_prompt, encoding="utf-8")

        # Build command — matches working CLI exactly
        cmd = [
            self.claude_path,
            "--print",
            "--model", self.model,
            "--permission-mode", "bypassPermissions",
            "--no-session-persistence",
            "--disallowedTools", "MCPSearch,ToolSearch",
        ]

        if max_turns:
            cmd.extend(["--max-turns", str(max_turns)])

        env = self._build_env()

        process_killed = False
        kill_reason = ""
        output_lines = []
        last_output_time = time.time()
        first_output_received = False
        process_start_time = time.time()

        try:
            # Open prompt file as stdin — exactly like CLI "< file.txt"
            prompt_handle = open(prompt_file, "r", encoding="utf-8")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=prompt_handle,
                env=env,
                text=False,
                bufsize=0,
                cwd=cwd,
            )

            prompt_handle.close()
            logger.info(f"[ClaudeEngine] Process started PID: {process.pid}")

            # Timeout monitor thread
            def monitor():
                nonlocal process_killed, kill_reason
                while process.poll() is None and not process_killed:
                    time.sleep(2)
                    elapsed = time.time() - process_start_time
                    if elapsed > timeout:
                        process_killed = True
                        kill_reason = f"timeout_{timeout}s"
                        process.kill()
                        break

            monitor_thread = threading.Thread(target=monitor, daemon=True)
            monitor_thread.start()

            # Read stdout line by line (unbuffered, real-time)
            for line in iter(process.stdout.readline, b""):
                if not line or process_killed:
                    break

                last_output_time = time.time()
                if not first_output_received:
                    first_output_received = True

                line_text = line.decode("utf-8", errors="ignore").rstrip("\n").rstrip("\r")
                if line_text:
                    output_lines.append(line_text)

            process.wait()
            stderr_output = process.stderr.read().decode("utf-8", errors="ignore") if process.stderr else ""

            if process_killed:
                raise RuntimeError(f"Claude Code timed out after {timeout}s")

            if process.returncode != 0:
                raise RuntimeError(f"Claude Code failed (exit {process.returncode}): {stderr_output[:300]}")

            # Join all output lines
            full_output = "\n".join(output_lines).strip()

            # Strip markdown fences
            if full_output.startswith("```"):
                lines = full_output.split("\n")
                if lines[-1].strip() == "```":
                    lines = lines[1:-1]
                elif lines[0].startswith("```"):
                    lines = lines[1:]
                full_output = "\n".join(lines).strip()

            elapsed = time.time() - process_start_time
            logger.info(f"[ClaudeEngine] Done in {elapsed:.1f}s, output {len(full_output)} chars")

            return {
                "result": full_output,
                "cost_usd": 0.0,
                "tokens": {},
                "tools_used": [],
                "elapsed_seconds": elapsed,
            }

        finally:
            try:
                prompt_file.unlink(missing_ok=True)
            except Exception:
                pass

    async def run(
        self,
        prompt: str,
        tools: list[str] | None = None,
        mcp_config: dict | None = None,
        json_schema: dict | None = None,
        max_turns: int | None = None,
        system_prompt: str | None = None,
        timeout: int = 600,
        cwd: str | None = None,
    ) -> dict:
        """Run Claude Code (async wrapper around sync Popen)."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            lambda: self._run_sync(prompt, system_prompt, max_turns, timeout, cwd),
        )

    async def stream(
        self,
        prompt: str,
        tools: list[str] | None = None,
        mcp_config: dict | None = None,
        system_prompt: str | None = None,
        max_turns: int | None = None,
        timeout: int = 3600,
        cwd: str | None = None,
    ):
        """Stream Claude Code output as events (for research agent progress)."""
        import asyncio

        execution_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        prompt_file = Path(tempfile.gettempdir()) / f"pedagora_prompt_{execution_id}.txt"
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n---\n\n{prompt}"
        prompt_file.write_text(full_prompt, encoding="utf-8")

        cmd = [
            self.claude_path,
            "--print",
            "--model", self.model,
            "--permission-mode", "bypassPermissions",
            "--no-session-persistence",
            "--disallowedTools", "MCPSearch,ToolSearch",
            "--output-format", "stream-json",
            "--verbose",
        ]

        if max_turns:
            cmd.extend(["--max-turns", str(max_turns)])

        env = self._build_env()
        import queue
        event_queue = queue.Queue()

        def run_process():
            start = time.time()
            try:
                handle = open(prompt_file, "r", encoding="utf-8")
                process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    stdin=handle, env=env, text=False, bufsize=0, cwd=cwd,
                )
                handle.close()

                for line in iter(process.stdout.readline, b""):
                    if not line:
                        break
                    if time.time() - start > timeout:
                        process.kill()
                        event_queue.put({"type": "error", "message": f"Timed out after {timeout}s"})
                        break

                    line_text = line.decode("utf-8", errors="ignore").strip()
                    if not line_text:
                        continue

                    try:
                        data = json.loads(line_text)
                        msg_type = data.get("type")

                        if msg_type == "assistant":
                            for block in data.get("message", {}).get("content", []):
                                if block.get("type") == "text" and block.get("text"):
                                    event_queue.put({"type": "text", "content": block["text"]})
                                elif block.get("type") == "tool_use":
                                    event_queue.put({"type": "tool_use", "name": block.get("name", ""), "input": block.get("input", {})})
                        elif msg_type == "result":
                            event_queue.put({"type": "result", "result": data.get("result", ""), "cost_usd": data.get("total_cost_usd", 0)})
                    except json.JSONDecodeError:
                        pass

                process.wait()
            except Exception as e:
                event_queue.put({"type": "error", "message": str(e)})
            finally:
                event_queue.put(None)  # Sentinel
                try:
                    prompt_file.unlink(missing_ok=True)
                except Exception:
                    pass

        # Run in thread, yield events from async
        thread = threading.Thread(target=run_process, daemon=True)
        thread.start()

        loop = asyncio.get_event_loop()
        while True:
            event = await loop.run_in_executor(None, event_queue.get)
            if event is None:
                break
            yield event
