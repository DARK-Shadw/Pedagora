"""NVIDIA NIM client for DeepSeek V4 Flash code generation.

Drop-in replacement for GeminiClient.generate_code() using deepseek-ai/deepseek-v4-flash
via NVIDIA's OpenAI-compatible NIM endpoint. Uses SSE streaming to avoid
gateway timeouts on the free tier.

Supports parallel calls via semaphore (default 4 concurrent). Each call
streams ~18K chars JS in ~8 minutes for complex browser animations.
"""

import asyncio
import json
import logging
import time

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

MODEL = "deepseek-ai/deepseek-v4-flash"
API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MAX_CONCURRENT_PER_KEY = 1
STREAM_TIMEOUT = httpx.Timeout(connect=30.0, read=600.0, write=30.0, pool=30.0)


class NvidiaClient:
    """NVIDIA NIM DeepSeek V4 Flash code generator — same interface as GeminiClient.

    Supports multiple API keys via NVIDIA_API_KEYS (comma-separated).
    Round-robins across keys to spread rate limits.
    """

    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        keys_str = settings.nvidia_api_keys or ""
        keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        if not keys:
            single = api_key or settings.nvidia_api_key
            if not single:
                raise ValueError("NVIDIA_API_KEY not configured")
            keys = [single]
        self._keys = keys
        self._key_idx = 0
        self._key_lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(MAX_CONCURRENT_PER_KEY * len(keys))
        self._stats = [{"ok": 0, "fail": 0, "last_429": 0.0} for _ in keys]
        logger.info(
            f"[NvidiaNIM] Initialized with model={MODEL}, "
            f"{len(keys)} key(s), concurrency={MAX_CONCURRENT_PER_KEY * len(keys)}"
        )

    async def _next_key(self) -> tuple[int, str]:
        async with self._key_lock:
            # Pick the key with the oldest 429 cooldown
            now = time.time()
            best = min(range(len(self._keys)), key=lambda i: self._stats[i]["last_429"])
            if self._stats[best]["last_429"] > now - 5:
                # All keys recently 429'd — just round-robin
                idx = self._key_idx % len(self._keys)
                self._key_idx += 1
            else:
                idx = best
                self._key_idx = idx + 1
            return idx, self._keys[idx]

    @property
    def pool_size(self) -> int:
        return MAX_CONCURRENT_PER_KEY * len(self._keys)

    def stats(self) -> list[dict]:
        return [
            {"key_index": i, "ok": s["ok"], "fail": s["fail"], "cooling": max(0, s["last_429"] - time.time() + 30)}
            for i, s in enumerate(self._stats)
        ]

    async def generate_code(
        self,
        *,
        prompt: str,
        system_prompt: str,
        max_output_tokens: int = 16384,
        temperature: float = 0.2,
        model: str | None = None,
        **kwargs,
    ) -> tuple[str, dict]:
        """Generate code via NVIDIA NIM with SSE streaming.

        Streaming avoids gateway timeouts on free tier — each chunk keeps
        the connection alive. Tokens are accumulated and returned as a
        complete response, same interface as the non-streaming version.
        """
        async with self._sem:
            t0 = time.time()
            key_idx, api_key = await self._next_key()

            payload = {
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_output_tokens,
                "stream": True,
                "chat_template_kwargs": {"thinking": False},
            }

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            }

            content_chunks: list[str] = []
            usage = {}
            last_error = None

            for attempt in range(3):
                content_chunks.clear()
                try:
                    async with httpx.AsyncClient(timeout=STREAM_TIMEOUT) as client:
                        async with client.stream(
                            "POST", API_URL,
                            headers=headers,
                            json=payload,
                        ) as resp:
                            if resp.status_code == 429:
                                self._stats[key_idx]["last_429"] = time.time()
                                # Try a different key on next attempt
                                key_idx, api_key = await self._next_key()
                                headers["Authorization"] = f"Bearer {api_key}"
                                wait = min(15 * (attempt + 1), 45)
                                logger.warning(f"[NvidiaNIM] 429 on key[{key_idx}], switching key, waiting {wait}s")
                                await asyncio.sleep(wait)
                                last_error = "429 rate limited"
                                continue

                            if resp.status_code >= 500:
                                body = ""
                                async for chunk in resp.aiter_text():
                                    body += chunk
                                    if len(body) > 500:
                                        break
                                wait = 10 * (attempt + 1)
                                logger.warning(
                                    f"[NvidiaNIM] {resp.status_code} server error, "
                                    f"retrying in {wait}s: {body[:200]}"
                                )
                                await asyncio.sleep(wait)
                                last_error = f"{resp.status_code} server error"
                                continue

                            if resp.status_code != 200:
                                body = ""
                                async for chunk in resp.aiter_text():
                                    body += chunk
                                    if len(body) > 500:
                                        break
                                raise RuntimeError(
                                    f"NVIDIA NIM HTTP {resp.status_code}: {body[:300]}"
                                )

                            # Stream SSE chunks
                            token_count = 0
                            async for line in resp.aiter_lines():
                                line = line.strip()
                                if not line or not line.startswith("data:"):
                                    continue
                                data_str = line[len("data:"):].strip()
                                if data_str == "[DONE]":
                                    break
                                try:
                                    chunk_data = json.loads(data_str)
                                    delta = chunk_data["choices"][0].get("delta", {})
                                    text = delta.get("content", "")
                                    if text:
                                        content_chunks.append(text)
                                        token_count += 1
                                        if token_count % 200 == 0:
                                            chars_so_far = sum(len(c) for c in content_chunks)
                                            logger.info(
                                                f"[NvidiaNIM] key[{key_idx}] Streaming... "
                                                f"{token_count} chunks, {chars_so_far} chars"
                                            )
                                    if "usage" in chunk_data and chunk_data["usage"]:
                                        usage = chunk_data["usage"]
                                except (json.JSONDecodeError, KeyError, IndexError):
                                    continue

                    # Stream completed successfully
                    break

                except httpx.TimeoutException:
                    self._stats[key_idx]["fail"] += 1
                    last_error = f"Timeout on attempt {attempt + 1} key[{key_idx}]"
                    if attempt < 2:
                        key_idx, api_key = await self._next_key()
                        headers["Authorization"] = f"Bearer {api_key}"
                        logger.warning(f"[NvidiaNIM] {last_error}, switching key, retrying...")
                        continue
                    raise RuntimeError(
                        f"NVIDIA NIM timed out after 3 attempts"
                    )
            else:
                raise RuntimeError(
                    f"NVIDIA NIM failed after 3 attempts (last: {last_error})"
                )

            elapsed = time.time() - t0
            self._stats[key_idx]["ok"] += 1

            content = "".join(content_chunks)
            if not content.strip():
                raise RuntimeError("NVIDIA DeepSeek returned empty streaming response")

            code = _extract_code(content)
            if not code:
                raise RuntimeError(
                    f"NVIDIA DeepSeek returned no extractable code; "
                    f"content[:300]={content[:300]!r}"
                )

            meta = {
                "elapsed_seconds": round(elapsed, 2),
                "model": MODEL,
                "key_index": key_idx,
                "tokens_in": usage.get("prompt_tokens"),
                "tokens_out": usage.get("completion_tokens"),
            }
            logger.info(
                f"[NvidiaNIM] key[{key_idx}] OK in {elapsed:.1f}s "
                f"({meta['tokens_in']}->{meta['tokens_out']} tok, {len(code)} chars)"
            )
            return code, meta


def _extract_code(content: str) -> str:
    """Extract code from JSON {"code": "..."}, markdown fences, or raw response."""
    content = content.strip()

    # Try JSON first (model may return bare JSON)
    code = _try_json_extract(content)
    if code:
        return code

    # Try markdown fences — model often wraps JSON in ```json ... ```
    if "```" in content:
        lines = content.split("\n")
        in_code = False
        code_lines = []
        for line in lines:
            if line.strip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                code_lines.append(line)
        if code_lines:
            inner = "\n".join(code_lines).strip()
            # The fenced content might be JSON {"code": "..."} — try extracting
            code = _try_json_extract(inner)
            if code:
                return code
            # Otherwise it's raw code inside fences
            return inner

    # Raw content — return as-is if it looks like code
    if any(marker in content for marker in [
        "class AnimationScene", "from manim import",
        "const ", "document.getElementById", "tl.addLabel",
    ]):
        return content.strip()

    return ""


def _try_json_extract(text: str) -> str:
    """Try to parse text as JSON and extract the 'code' field."""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            code = (parsed.get("code") or "").strip()
            if code:
                return code
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return ""
