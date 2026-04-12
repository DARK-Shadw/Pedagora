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
        """Run Claude Code using -p flag with Read/Write tools.

        Writes prompt to a temp file, tells Claude to read it and write output
        to another temp file. This matches interactive mode behavior and avoids
        stdin piping issues that cause hangs/500 errors.
        """
        execution_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        # Write prompt to temp file
        prompt_file = Path(tempfile.gettempdir()) / f"pedagora_prompt_{execution_id}.txt"
        output_file = Path(tempfile.gettempdir()) / f"pedagora_output_{execution_id}.txt"
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n---\n\n{prompt}"
        prompt_file.write_text(full_prompt, encoding="utf-8")

        # Clean output file if exists
        if output_file.exists():
            output_file.unlink()

        # Build command with -p flag (inline instruction)
        prompt_path = str(prompt_file).replace("\\", "/")
        output_path = str(output_file).replace("\\", "/")

        cmd = [
            self.claude_path,
            "--print",
            "--model", self.model,
            "--permission-mode", "bypassPermissions",
            "--no-session-persistence",
            "--disallowedTools", "MCPSearch,ToolSearch",
            "--allowedTools", "Read,Write",
            "-p", f"Read {prompt_path} and follow the instructions in it. "
                  f"Write your complete response to {output_path}",
        ]

        if max_turns:
            cmd.extend(["--max-turns", str(max_turns)])

        env = self._build_env()

        process_killed = False
        process_start_time = time.time()

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=False,
                bufsize=0,
                cwd=cwd,
            )

            logger.info(
                f"[ClaudeEngine] Process started PID: {process.pid} "
                f"model={self.model} timeout={timeout}s"
            )

            # Timeout monitor thread + heartbeat (so long Opus calls don't
            # look like the server is hung)
            def monitor():
                nonlocal process_killed
                last_heartbeat = process_start_time
                while process.poll() is None and not process_killed:
                    time.sleep(2)
                    now = time.time()
                    elapsed = now - process_start_time
                    if elapsed > timeout:
                        process_killed = True
                        process.kill()
                        break
                    if now - last_heartbeat >= 30:
                        logger.info(
                            f"[ClaudeEngine] still working… {int(elapsed)}s elapsed "
                            f"(timeout {timeout}s, model={self.model})"
                        )
                        last_heartbeat = now

            monitor_thread = threading.Thread(target=monitor, daemon=True)
            monitor_thread.start()

            # Drain stdout and stderr concurrently — stderr in a separate
            # thread so the subprocess can't deadlock filling its pipe buffer,
            # AND so we still have its contents on non-zero exit.
            stdout_chunks: list[bytes] = []
            stderr_chunks: list[bytes] = []

            def _drain_stderr():
                if not process.stderr:
                    return
                for chunk in iter(process.stderr.readline, b""):
                    if not chunk:
                        break
                    stderr_chunks.append(chunk)

            stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
            stderr_thread.start()

            for line in iter(process.stdout.readline, b""):
                if not line or process_killed:
                    break
                stdout_chunks.append(line)

            process.wait()
            stderr_thread.join(timeout=2)

            stdout_text = b"".join(stdout_chunks).decode("utf-8", errors="ignore")
            stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="ignore")

            if process_killed:
                raise RuntimeError(f"Claude Code timed out after {timeout}s")

            if process.returncode != 0:
                # Surface stderr first; if empty, fall back to stdout tail and
                # whether the output file was even touched. Empty-stderr exits
                # usually mean the CLI rejected an arg (e.g. unknown --model
                # alias) and printed nothing useful.
                detail = stderr_text.strip()
                if not detail:
                    detail = (
                        f"(empty stderr) stdout_tail={stdout_text[-300:]!r} "
                        f"output_file_exists={output_file.exists()} "
                        f"model={self.model!r}"
                    )
                logger.error(
                    f"[ClaudeEngine] exit {process.returncode} | model={self.model} "
                    f"| stderr={stderr_text[:500]!r} | stdout_tail={stdout_text[-300:]!r}"
                )
                raise RuntimeError(
                    f"Claude Code failed (exit {process.returncode}): {detail[:500]}"
                )

            # Read the output file Claude wrote
            if not output_file.exists():
                raise RuntimeError("Claude did not write output file")

            full_output = output_file.read_text(encoding="utf-8").strip()

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
            for f in [prompt_file, output_file]:
                try:
                    f.unlink(missing_ok=True)
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
