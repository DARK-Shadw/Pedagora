"""Groq-based code generator for Animation Agent v2.

Drop-in replacement for GeminiClient.generate_code() when Gemini quota is
exhausted. Uses openai/gpt-oss-120b (8000 TPM free tier).

Rate limit: 8000 TPM with ~5-7K tokens per frame means we must serialize
requests with ~60s cooldown between frames. The client handles this
internally.
"""

import asyncio
import logging
import time

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

MODEL = "openai/gpt-oss-120b"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
TPM_LIMIT = 8000
COOLDOWN_AFTER_CALL = 62.0  # wait 62s between calls for TPM to reset


class GroqCodeClient:
    """Sequential Groq code generator with TPM-aware pacing."""

    def __init__(self):
        settings = get_settings()
        self._api_key = settings.groq_api_key
        if not self._api_key:
            raise ValueError("GROQ_API_KEY not configured")
        self._lock = asyncio.Lock()
        self._last_call: float = 0.0
        self._call_count = 0
        logger.info(f"[GroqCode] Initialized with model={MODEL}")

    @property
    def pool_size(self) -> int:
        return 1

    async def generate_code(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> tuple[str, dict]:
        """Generate JS code via Groq. Same interface as GeminiClient.generate_code."""
        async with self._lock:
            # Enforce TPM cooldown
            elapsed_since_last = time.monotonic() - self._last_call
            if self._last_call > 0 and elapsed_since_last < COOLDOWN_AFTER_CALL:
                wait = COOLDOWN_AFTER_CALL - elapsed_since_last
                logger.info(f"[GroqCode] TPM cooldown: waiting {wait:.0f}s")
                await asyncio.sleep(wait)

            t0 = time.time()
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    GROQ_API_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt + "\n\nReturn ONLY raw JavaScript code. No markdown fences, no explanation."},
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )

            self._last_call = time.monotonic()
            self._call_count += 1
            elapsed = time.time() - t0

            if resp.status_code == 429:
                error_msg = resp.text[:200]
                logger.warning(f"[GroqCode] 429 rate limited: {error_msg}")
                # Wait and retry once
                await asyncio.sleep(65.0)
                self._last_call = time.monotonic()
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(
                        GROQ_API_URL,
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": MODEL,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": prompt + "\n\nReturn ONLY raw JavaScript code. No markdown fences, no explanation."},
                            ],
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                        },
                    )
                elapsed = time.time() - t0

            if resp.status_code != 200:
                raise RuntimeError(
                    f"Groq API error {resp.status_code}: {resp.text[:300]}"
                )

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})

            # Strip markdown fences if model wraps code
            code = _strip_markdown_fences(content)

            logger.info(
                f"[GroqCode] Generated {len(code)} chars in {elapsed:.1f}s "
                f"(call #{self._call_count}, "
                f"tokens: {usage.get('prompt_tokens', '?')}->{usage.get('completion_tokens', '?')})"
            )

            meta = {
                "model": MODEL,
                "elapsed_seconds": elapsed,
                "tokens_in": usage.get("prompt_tokens"),
                "tokens_out": usage.get("completion_tokens"),
                "key_index": 0,
            }
            return code, meta


def _strip_markdown_fences(content: str) -> str:
    """Remove ```javascript / ```js / ``` wrappers if present."""
    if "```" not in content:
        return content.strip()

    lines = content.split("\n")
    in_code = False
    code_lines = []
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(line)

    return "\n".join(code_lines).strip() if code_lines else content.strip()
