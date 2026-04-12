"""Gemini 3.1 Flash Lite client with multi-key pool + structured output.

Used by the Animation Agent v2 generator. Wraps the sync `google.genai` SDK in an
async-friendly interface via `asyncio.to_thread`, enforces a 15 RPM throttle per
key, rotates keys on 429 / 5xx / auth errors, and returns parsed code from
Gemini's JSON structured-output response.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

logger = logging.getLogger(__name__)

MODEL_ID = "gemini-3.1-flash-lite-preview"
RPM_PER_KEY = 15
MIN_INTERVAL = 60.0 / RPM_PER_KEY          # 4.0s between calls on the same key
RATE_LIMIT_COOLDOWN = 60.0                 # 429 -> cool key 60s
AUTH_COOLDOWN = 600.0                      # 401/403 -> cool key 10 min
TRANSIENT_COOLDOWN = 10.0                  # 5xx -> cool key 10s

# JSON schema Gemini is forced to emit: a single object with a "code" string.
CODE_SCHEMA = {
    "type": "object",
    "properties": {"code": {"type": "string"}},
    "required": ["code"],
}


@dataclass
class _KeyState:
    key: str
    client: "genai.Client"
    last_call: float = 0.0
    cooling_until: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    fail_count: int = 0
    ok_count: int = 0


class GeminiPoolExhausted(RuntimeError):
    """Raised when every key in the pool is cooling and max rotations is reached."""


class GeminiClient:
    """Round-robin Gemini client over a pool of API keys.

    Usage:
        gemini = GeminiClient(["key1", "key2", "key3"])
        code, meta = await gemini.generate_code(
            prompt="...",
            system_prompt="...",
        )
    """

    def __init__(self, api_keys: list[str]):
        if not api_keys:
            raise ValueError("GeminiClient requires at least one API key")
        self._states: list[_KeyState] = [
            _KeyState(key=k, client=genai.Client(api_key=k)) for k in api_keys
        ]
        self._rr_lock = asyncio.Lock()
        self._rr_index = 0
        logger.info(f"[Gemini] Pool initialized with {len(self._states)} key(s), model={MODEL_ID}")

    @property
    def pool_size(self) -> int:
        return len(self._states)

    def stats(self) -> list[dict]:
        return [
            {
                "key_index": i,
                "ok": s.ok_count,
                "fail": s.fail_count,
                "cooling": max(0.0, s.cooling_until - time.monotonic()),
            }
            for i, s in enumerate(self._states)
        ]

    async def _pick_key(self) -> _KeyState:
        """Return the next usable key. If all are cooling, sleep until the earliest is free."""
        async with self._rr_lock:
            now = time.monotonic()
            n = len(self._states)
            for i in range(n):
                idx = (self._rr_index + i) % n
                st = self._states[idx]
                if st.cooling_until <= now:
                    self._rr_index = (idx + 1) % n
                    return st
            # All cooling — pick the one with earliest expiry and wait outside the RR lock.
            earliest = min(self._states, key=lambda s: s.cooling_until)
            wait = max(0.0, earliest.cooling_until - now)
        if wait > 0:
            logger.warning(
                f"[Gemini] All {len(self._states)} keys cooling, sleeping {wait:.1f}s"
            )
            await asyncio.sleep(wait)
        return earliest

    async def generate_code(
        self,
        *,
        prompt: str,
        system_prompt: str,
        max_output_tokens: int = 8192,
        temperature: float = 0.2,
        max_key_rotations: int = 4,
        model: str | None = None,
    ) -> tuple[str, dict]:
        """Generate code via Gemini structured output.

        Returns:
            (code, meta) where code is the `code` field of the JSON response and
            meta is a dict with elapsed_seconds / key_index / tokens_in / tokens_out.

        Raises:
            GeminiPoolExhausted: if every key rotation hit rate-limit / auth / 5xx.
            RuntimeError: on malformed structured output (parse failure / empty code).
            ClientError: on non-retryable 4xx (propagated so caller surfaces real bugs).
        """
        use_model = model or MODEL_ID
        last_exc: Exception | None = None

        for rotation in range(max_key_rotations):
            st = await self._pick_key()
            key_index = self._states.index(st)

            async with st.lock:
                # 15 RPM per key: enforce min interval between successive calls on the same key.
                gap = time.monotonic() - st.last_call
                if gap < MIN_INTERVAL:
                    await asyncio.sleep(MIN_INTERVAL - gap)

                t0 = time.monotonic()
                try:
                    resp = await asyncio.to_thread(
                        st.client.models.generate_content,
                        model=use_model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            temperature=temperature,
                            max_output_tokens=max_output_tokens,
                            response_mime_type="application/json",
                            response_schema=CODE_SCHEMA,
                        ),
                    )
                    st.last_call = time.monotonic()
                except ClientError as e:  # 4xx
                    st.last_call = time.monotonic()
                    last_exc = e
                    status = getattr(e, "status_code", None) or getattr(e, "code", None)
                    err_str = str(e)
                    if status == 429 or "RESOURCE_EXHAUSTED" in err_str:
                        st.cooling_until = time.monotonic() + RATE_LIMIT_COOLDOWN
                        st.fail_count += 1
                        logger.warning(
                            f"[Gemini] key#{key_index} rate-limited (429), "
                            f"cooling {RATE_LIMIT_COOLDOWN:.0f}s, rotating..."
                        )
                        continue
                    if status in (401, 403) or "PERMISSION_DENIED" in err_str or "API key" in err_str:
                        st.cooling_until = time.monotonic() + AUTH_COOLDOWN
                        st.fail_count += 1
                        logger.error(
                            f"[Gemini] key#{key_index} auth error ({status}), "
                            f"cooling {AUTH_COOLDOWN:.0f}s, rotating: {err_str[:200]}"
                        )
                        continue
                    # Other 4xx = bad request / schema bug — don't burn more keys.
                    st.fail_count += 1
                    raise
                except ServerError as e:  # 5xx
                    st.last_call = time.monotonic()
                    last_exc = e
                    st.cooling_until = time.monotonic() + TRANSIENT_COOLDOWN
                    st.fail_count += 1
                    logger.warning(
                        f"[Gemini] key#{key_index} 5xx error, "
                        f"cooling {TRANSIENT_COOLDOWN:.0f}s, rotating: {str(e)[:200]}"
                    )
                    continue

                elapsed = time.monotonic() - t0
                raw_text = resp.text or ""

                try:
                    parsed = json.loads(raw_text)
                    code = (parsed.get("code") or "").strip()
                except Exception as parse_err:
                    st.fail_count += 1
                    raise RuntimeError(
                        f"Gemini structured-output JSON parse failed: {parse_err}; "
                        f"raw[:300]={raw_text[:300]!r}"
                    )

                if not code:
                    st.fail_count += 1
                    raise RuntimeError(
                        f"Gemini returned empty 'code' field; raw[:300]={raw_text[:300]!r}"
                    )

                usage = getattr(resp, "usage_metadata", None)
                meta = {
                    "elapsed_seconds": round(elapsed, 2),
                    "key_index": key_index,
                    "model": use_model,
                    "tokens_in": getattr(usage, "prompt_token_count", None) if usage else None,
                    "tokens_out": getattr(usage, "candidates_token_count", None) if usage else None,
                }
                st.ok_count += 1
                logger.info(
                    f"[Gemini] key#{key_index} OK in {elapsed:.1f}s "
                    f"({meta['tokens_in']}->{meta['tokens_out']} tok, {len(code)} chars)"
                )
                return code, meta

        raise GeminiPoolExhausted(
            f"All {len(self._states)} Gemini keys exhausted after "
            f"{max_key_rotations} rotations (last error: {last_exc})"
        )
