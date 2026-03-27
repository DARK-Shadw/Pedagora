"""
ClaudeEngine — Python wrapper for Claude Code CLI.

Enables using Claude Code (Opus/Sonnet) as the AI engine for all Pedagora
agents: Research, Course Planner, Animation, and Teacher. Uses the user's
Claude Code subscription (no API key needed).

Features:
- Non-interactive execution via `claude -p`
- Structured JSON output with schema validation
- Streaming output for real-time teacher control
- MCP server integration for custom tools
- Subscription auth (removes ANTHROPIC_API_KEY to force logged-in account)
- File-based prompts to avoid CLI truncation issues
"""

import asyncio
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
from typing import Any, AsyncGenerator, Optional

logger = logging.getLogger(__name__)


class ClaudeEngine:
    """Wraps Claude Code CLI for programmatic use."""

    def __init__(self, model: str = "sonnet"):
        self.model = model
        self.claude_path = self._find_claude_path()
        logger.info(f"[ClaudeEngine] Initialized: claude={self.claude_path}, model={model}")

    def _find_claude_path(self) -> str:
        """Find the claude binary on the system."""
        if os.name == "nt":
            path = shutil.which("claude")
            if path:
                return path
            appdata = Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "claude" / "claude.exe"
            if appdata.exists():
                return str(appdata)
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
        raise RuntimeError("Claude Code CLI not found. Install: npm install -g @anthropic-ai/claude-code")

    def _build_env(self) -> dict:
        """Build environment for subprocess — subscription auth, no CLAUDECODE."""
        env = os.environ.copy()
        # Remove CLAUDECODE to prevent "cannot launch inside another session" error
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)
        # Remove API key to force subscription auth
        env.pop("ANTHROPIC_API_KEY", None)
        # Disable MCP tool search to prevent API 400 errors
        env["ENABLE_TOOL_SEARCH"] = "false"
        return env

    def _write_prompt_file(self, prompt: str, execution_id: str) -> Path:
        """Write prompt to temp file (avoids CLI truncation on Windows)."""
        path = Path(tempfile.gettempdir()) / f"pedagora_prompt_{execution_id}.txt"
        path.write_text(prompt, encoding="utf-8")
        return path

    def _write_mcp_config(self, mcp_config: dict, execution_id: str) -> Path:
        """Write MCP config to temp file."""
        path = Path(tempfile.gettempdir()) / f"pedagora_mcp_{execution_id}.json"
        path.write_text(json.dumps(mcp_config, indent=2), encoding="utf-8")
        return path

    def _build_cmd(
        self,
        tools: list[str] | None = None,
        mcp_config_path: str | None = None,
        json_schema: dict | None = None,
        max_turns: int | None = None,
        system_prompt: str | None = None,
        streaming: bool = False,
    ) -> list[str]:
        """Build the claude CLI command."""
        cmd = [
            self.claude_path,
            "--print",
            "--model", self.model,
            "--permission-mode", "bypassPermissions",
            "--no-session-persistence",
            "--disallowedTools", "MCPSearch,ToolSearch",
        ]

        if streaming:
            cmd.extend(["--output-format", "stream-json", "--verbose", "--include-partial-messages"])
        else:
            cmd.extend(["--output-format", "json"])

        if tools:
            cmd.extend(["--allowedTools", ",".join(tools)])

        if mcp_config_path:
            cmd.extend(["--mcp-config", mcp_config_path])

        if json_schema:
            cmd.extend(["--json-schema", json.dumps(json_schema)])

        if max_turns:
            cmd.extend(["--max-turns", str(max_turns)])

        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])

        return cmd

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
        """
        Run Claude Code non-interactively and return the result.

        Args:
            prompt: The task/question for Claude
            tools: List of allowed tools (e.g., ["WebSearch", "WebFetch", "Read", "Write", "Bash"])
            mcp_config: Optional MCP server config dict
            json_schema: Optional JSON schema for structured output validation
            max_turns: Max agent turns (limits tool use iterations)
            system_prompt: Custom system prompt (replaces default)
            timeout: Max execution time in seconds
            cwd: Working directory for execution

        Returns:
            dict with keys: result (str), cost_usd (float), tokens (dict), tools_used (list)
        """
        execution_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        prompt_file = None
        mcp_file = None

        try:
            # Write prompt to file
            prompt_file = self._write_prompt_file(prompt, execution_id)

            # Write MCP config if provided
            mcp_config_path = None
            if mcp_config:
                mcp_file = self._write_mcp_config(mcp_config, execution_id)
                mcp_config_path = str(mcp_file)

            # Build command
            cmd = self._build_cmd(
                tools=tools,
                mcp_config_path=mcp_config_path,
                json_schema=json_schema,
                max_turns=max_turns,
                system_prompt=system_prompt,
                streaming=False,
            )

            env = self._build_env()
            logger.info(f"[ClaudeEngine] Running: {' '.join(cmd[:6])}...")

            # Run subprocess with prompt piped via stdin
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
            )

            # Read prompt and pipe to stdin
            prompt_text = prompt_file.read_text(encoding="utf-8")
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=prompt_text.encode("utf-8")),
                timeout=timeout,
            )

            output = stdout.decode("utf-8", errors="ignore").strip()

            if process.returncode != 0:
                # Try to parse JSON error
                try:
                    data = json.loads(output)
                    error_msg = data.get("result", output)
                except json.JSONDecodeError:
                    error_msg = output or stderr.decode("utf-8", errors="ignore")
                raise RuntimeError(f"Claude Code failed (exit {process.returncode}): {error_msg}")

            # Parse JSON result
            try:
                data = json.loads(output)
            except json.JSONDecodeError:
                # Non-JSON output — return as plain text
                return {
                    "result": output,
                    "cost_usd": 0.0,
                    "tokens": {},
                    "tools_used": [],
                }

            result_text = data.get("result", "")
            usage = data.get("usage", {})
            cost = data.get("total_cost_usd", 0.0)

            # Strip markdown code fences if present (Claude wraps JSON in ```json...```)
            stripped = result_text.strip()
            if stripped.startswith("```"):
                lines = stripped.split("\n")
                # Remove first line (```json) and last line (```)
                if lines[-1].strip() == "```":
                    lines = lines[1:-1]
                elif lines[0].startswith("```"):
                    lines = lines[1:]
                stripped = "\n".join(lines).strip()
                # Try to parse as JSON — if successful, use the stripped version
                try:
                    json.loads(stripped)
                    result_text = stripped
                except json.JSONDecodeError:
                    pass  # Keep original

            return {
                "result": result_text,
                "cost_usd": cost,
                "tokens": {
                    "input": usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0),
                    "output": usage.get("output_tokens", 0),
                },
                "tools_used": [],
                "raw": data,
            }

        except asyncio.TimeoutError:
            raise RuntimeError(f"Claude Code timed out after {timeout}s")
        finally:
            # Cleanup temp files
            for f in [prompt_file, mcp_file]:
                if f and f.exists():
                    try:
                        f.unlink()
                    except Exception:
                        pass

    async def stream(
        self,
        prompt: str,
        tools: list[str] | None = None,
        mcp_config: dict | None = None,
        system_prompt: str | None = None,
        max_turns: int | None = None,
        timeout: int = 3600,
        cwd: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Stream Claude Code output as events for real-time use.

        Yields dicts with type: "text", "tool_use", "tool_result", "result", "error"
        """
        execution_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        prompt_file = None
        mcp_file = None

        try:
            prompt_file = self._write_prompt_file(prompt, execution_id)

            mcp_config_path = None
            if mcp_config:
                mcp_file = self._write_mcp_config(mcp_config, execution_id)
                mcp_config_path = str(mcp_file)

            cmd = self._build_cmd(
                tools=tools,
                mcp_config_path=mcp_config_path,
                system_prompt=system_prompt,
                max_turns=max_turns,
                streaming=True,
            )

            env = self._build_env()

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
            )

            # Send prompt via stdin
            prompt_text = prompt_file.read_text(encoding="utf-8")
            process.stdin.write(prompt_text.encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()

            start_time = time.time()

            # Read stdout line by line
            while True:
                if time.time() - start_time > timeout:
                    process.kill()
                    yield {"type": "error", "message": f"Timed out after {timeout}s"}
                    break

                try:
                    line = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=600,  # 10 min inactivity (WebFetch can be slow)
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    yield {"type": "error", "message": "Inactivity timeout (600s)"}
                    break

                if not line:
                    break

                line_text = line.decode("utf-8", errors="ignore").strip()
                if not line_text:
                    continue

                try:
                    data = json.loads(line_text)
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type")

                if msg_type == "assistant":
                    message = data.get("message", {})
                    for block in message.get("content", []):
                        if block.get("type") == "text" and block.get("text"):
                            yield {"type": "text", "content": block["text"]}
                        elif block.get("type") == "tool_use":
                            yield {
                                "type": "tool_use",
                                "name": block.get("name", ""),
                                "input": block.get("input", {}),
                            }

                elif msg_type == "result":
                    yield {
                        "type": "result",
                        "result": data.get("result", ""),
                        "cost_usd": data.get("total_cost_usd", 0.0),
                        "tokens": data.get("usage", {}),
                    }

            await process.wait()

        finally:
            for f in [prompt_file, mcp_file]:
                if f and f.exists():
                    try:
                        f.unlink()
                    except Exception:
                        pass
