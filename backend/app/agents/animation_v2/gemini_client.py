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

MODEL_ID = "gemini-3-flash-preview"
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

    def __init__(
        self,
        api_keys: list[str],
        paid_key: str | None = None,
        paid_model: str | None = None,
    ):
        if not api_keys:
            raise ValueError("GeminiClient requires at least one API key")
        self._states: list[_KeyState] = [
            _KeyState(key=k, client=genai.Client(api_key=k)) for k in api_keys
        ]
        self._rr_lock = asyncio.Lock()
        self._rr_index = 0

        self._paid_state: _KeyState | None = None
        self._paid_model: str | None = None
        if paid_key:
            self._paid_state = _KeyState(
                key=paid_key, client=genai.Client(api_key=paid_key)
            )
            self._paid_model = paid_model or MODEL_ID
            logger.info(
                f"[Gemini] Pool: {len(self._states)} free key(s) + "
                f"PAID fallback (model={self._paid_model})"
            )
        else:
            logger.info(
                f"[Gemini] Pool: {len(self._states)} free key(s), "
                f"model={MODEL_ID}, no paid fallback"
            )

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
        max_output_tokens: int | None = None,
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
                            **({"max_output_tokens": max_output_tokens} if max_output_tokens else {}),
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
                    code = _salvage_truncated_code(raw_text)
                    if code:
                        logger.warning(
                            f"[Gemini] key#{key_index} JSON truncated, "
                            f"salvaged {len(code)} chars of code"
                        )
                    else:
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

        # ── Free pool exhausted — try paid key fallback ──
        if self._paid_state:
            paid_model = self._paid_model or MODEL_ID
            logger.warning(
                f"[Gemini] ⚠ FREE POOL EXHAUSTED after {max_key_rotations} rotations "
                f"(last: {last_exc}) — FALLING BACK TO PAID KEY "
                f"(model={paid_model})"
            )
            return await self._call_paid(
                prompt=prompt,
                system_prompt=system_prompt,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                model=paid_model,
            )

        raise GeminiPoolExhausted(
            f"All {len(self._states)} Gemini keys exhausted after "
            f"{max_key_rotations} rotations (last error: {last_exc})"
        )

    async def _call_paid(
        self,
        *,
        prompt: str,
        system_prompt: str,
        max_output_tokens: int | None,
        temperature: float,
        model: str,
    ) -> tuple[str, dict]:
        """Single attempt on the paid key. No rotation — errors propagate."""
        st = self._paid_state
        assert st is not None

        async with st.lock:
            t0 = time.monotonic()
            resp = await asyncio.to_thread(
                st.client.models.generate_content,
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=temperature,
                    **({"max_output_tokens": max_output_tokens} if max_output_tokens else {}),
                    response_mime_type="application/json",
                    response_schema=CODE_SCHEMA,
                ),
            )
            st.last_call = time.monotonic()
            elapsed = time.monotonic() - t0

            raw_text = resp.text or ""
            try:
                parsed = json.loads(raw_text)
                code = (parsed.get("code") or "").strip()
            except Exception:
                code = _salvage_truncated_code(raw_text)
                if code:
                    logger.warning(
                        f"[Gemini] PAID key JSON truncated, "
                        f"salvaged {len(code)} chars"
                    )

            if not code:
                st.fail_count += 1
                raise RuntimeError(
                    f"Gemini PAID key returned no code; raw[:300]={raw_text[:300]!r}"
                )

            usage = getattr(resp, "usage_metadata", None)
            meta = {
                "elapsed_seconds": round(elapsed, 2),
                "key_index": "PAID",
                "model": model,
                "tokens_in": getattr(usage, "prompt_token_count", None) if usage else None,
                "tokens_out": getattr(usage, "candidates_token_count", None) if usage else None,
            }
            st.ok_count += 1
            logger.info(
                f"[Gemini] PAID KEY OK in {elapsed:.1f}s "
                f"({meta['tokens_in']}->{meta['tokens_out']} tok, "
                f"{len(code)} chars, model={model})"
            )
            return code, meta


def _salvage_truncated_code(raw: str) -> str:
    """Extract code from a truncated JSON response like {"code": "...

    When max_output_tokens is hit, Gemini cuts off mid-JSON-string.
    We recover the code by finding the opening quote after "code" and
    unescaping the rest, regardless of whitespace formatting.
    """
    import re
    m = re.search(r'"code"\s*:\s*"', raw)
    if not m:
        return ""
    code_escaped = raw[m.end():]
    if code_escaped.endswith('"}'):
        code_escaped = code_escaped[:-2]
    elif code_escaped.endswith('"'):
        code_escaped = code_escaped[:-1]
    try:
        code = json.loads('"' + code_escaped + '"')
    except json.JSONDecodeError:
        code = (
            code_escaped
            .replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace('\\"', '"')
            .replace("\\'", "'")
            .replace("\\\\", "\\")
        )
    return code.strip() if code.strip() else ""
