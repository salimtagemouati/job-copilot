"""
Unified multi-provider LLM router for AI Job Copilot.

Routing logic (automatic, based on model name prefix):
  "claude-*"  -> Anthropic SDK
  "gemini-*"  -> Google GenAI SDK (REST, not gRPC — avoids SSL issues)

Features:
  - Per-call provider detection — no manual switching
  - Retry with exponential backoff (max_retries from config)
  - Automatic Gemini -> Claude fallback on quota/5xx errors
  - Unified cost logging for both providers
  - Pydantic output parsing with JSON-fence stripping
  - LLMFailureException — never silently returns garbage

Cost reference (per 1M tokens):
  Claude Sonnet : $3.00 input / $15.00 output
  Gemini Flash  : $0.15 input / $0.60  output
"""

import json
import re
import time
from typing import TypeVar, Type

import anthropic
from google import genai as google_genai
from google.genai import types as genai_types
from pydantic import BaseModel, ValidationError

from config import settings
from utils.logger import get_logger, log_llm_call

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMFailureException(Exception):
    """Raised when LLM call exhausts all retries or Pydantic validation fails."""
    pass


# ── Singleton clients ─────────────────────────────────────────────────────────

_anthropic_client: anthropic.Anthropic | None = None
_gemini_client: google_genai.Client | None = None


def _get_anthropic() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


def _get_gemini() -> google_genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = google_genai.Client(api_key=settings.gemini_api_key)
    return _gemini_client


# ── Provider detection ────────────────────────────────────────────────────────

def _is_gemini(model: str) -> bool:
    return model.startswith("gemini-")


def _is_claude(model: str) -> bool:
    return model.startswith("claude-")


# ── Cost logging ──────────────────────────────────────────────────────────────

def _estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Returns estimated USD cost for a call."""
    if _is_gemini(model):
        input_cost  = (tokens_in  / 1_000_000) * settings.gemini_flash_input_cost
        output_cost = (tokens_out / 1_000_000) * settings.gemini_flash_output_cost
    else:
        input_cost  = (tokens_in  / 1_000_000) * settings.claude_sonnet_input_cost
        output_cost = (tokens_out / 1_000_000) * settings.claude_sonnet_output_cost
    return round(input_cost + output_cost, 5)


# ── Core call: Anthropic ──────────────────────────────────────────────────────

def _call_anthropic(
    model: str,
    prompt: str,
    system: str,
    max_tokens: int,
    purpose: str,
) -> str:
    client = _get_anthropic()
    start = time.time()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    duration_ms = (time.time() - start) * 1000
    tokens_in  = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    cost       = _estimate_cost(model, tokens_in, tokens_out)
    log_llm_call(logger, model, tokens_in, tokens_out, duration_ms, purpose, cost)
    return response.content[0].text


# ── Core call: Gemini ─────────────────────────────────────────────────────────

def _call_gemini(
    model: str,
    prompt: str,
    system: str,
    max_tokens: int,
    purpose: str,
) -> str:
    client = _get_gemini()
    request_model = model
    start = time.time()
    config = genai_types.GenerateContentConfig(
        system_instruction=system or None,
        max_output_tokens=max_tokens,
        temperature=0.1,       # low temp = more deterministic JSON
        response_mime_type="application/json",
    )

    try:
        response = client.models.generate_content(
            model=request_model,
            contents=prompt,
            config=config,
        )
    except Exception as e:
        err_str = str(e).lower()
        if (
            request_model == "gemini-2.5-flash-preview-04-17"
            and "404" in err_str
            and "not found" in err_str
        ):
            request_model = "gemini-2.5-flash"
            logger.warning(
                f"[{purpose}] gemini-2.5-flash-preview-04-17 unavailable; "
                f"retrying with {request_model}"
            )
            start = time.time()
            response = client.models.generate_content(
                model=request_model,
                contents=prompt,
                config=config,
            )
        else:
            raise
    duration_ms = (time.time() - start) * 1000

    # Token counting — Gemini returns usage_metadata
    meta = getattr(response, "usage_metadata", None)
    tokens_in  = getattr(meta, "prompt_token_count", 0)     or 0
    tokens_out = getattr(meta, "candidates_token_count", 0) or 0
    cost       = _estimate_cost(request_model, tokens_in, tokens_out)
    log_llm_call(logger, request_model, tokens_in, tokens_out, duration_ms, purpose, cost)

    return response.text


# ── Unified call (with retry + fallback) ─────────────────────────────────────

def call_llm(
    prompt: str,
    model: str,
    system: str = "You are a precise assistant. Return ONLY valid JSON. No preamble. No backticks.",
    max_tokens: int = 2048,
    purpose: str = "llm_call",
) -> str:
    """
    Makes an LLM call to Anthropic or Gemini based on the model name prefix.

    Retries up to settings.max_retries with exponential backoff.
    On Gemini quota/server errors, falls back to settings.gemini_fallback_model
    if settings.enable_fallback is True.

    Args:
        prompt:     User message / full prompt
        model:      Model name (e.g. "claude-sonnet-4-20250514" or "gemini-2.5-flash-preview-04-17")
        system:     System prompt
        max_tokens: Max output tokens
        purpose:    Label for cost/logging (e.g. "parse_job", "score_fit")

    Returns:
        Raw string response from the model

    Raises:
        LLMFailureException: If all retries and fallback exhausted
    """
    last_error: Exception | None = None
    models_to_try: list[str] = [model]

    # Add fallback model if enabled and primary is Gemini
    if settings.enable_fallback and _is_gemini(model):
        models_to_try.append(settings.gemini_fallback_model)

    for model_attempt in models_to_try:
        is_fallback = model_attempt != model
        if is_fallback:
            logger.warning(f"[{purpose}] Falling back to {model_attempt}")

        for attempt in range(settings.max_retries + 1):
            if attempt > 0:
                wait = settings.retry_delay_seconds * (2 ** (attempt - 1))
                logger.warning(f"[{purpose}] Retry {attempt}/{settings.max_retries} after {wait:.0f}s")
                time.sleep(wait)

            try:
                if _is_gemini(model_attempt):
                    return _call_gemini(model_attempt, prompt, system, max_tokens, purpose)
                elif _is_claude(model_attempt):
                    return _call_anthropic(model_attempt, prompt, system, max_tokens, purpose)
                else:
                    raise LLMFailureException(
                        f"Unknown model provider for '{model_attempt}'. "
                        "Model must start with 'claude-' or 'gemini-'."
                    )

            except LLMFailureException:
                raise   # propagate immediately — not a transient error

            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                # Don't retry on quota errors — move to fallback immediately
                if any(kw in err_str for kw in ["quota", "resource_exhausted", "429"]):
                    logger.warning(f"[{purpose}] Quota hit on {model_attempt}: {e}")
                    break  # skip remaining retries for this model, try fallback
                logger.error(f"[{purpose}] {model_attempt} attempt {attempt+1} failed: {e}")

    raise LLMFailureException(
        f"[{purpose}] All providers and retries exhausted. Last error: {last_error}"
    )


# ── JSON cleaning ─────────────────────────────────────────────────────────────

def _clean_json(raw: str) -> str:
    """Strips markdown code fences and leading/trailing whitespace."""
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    return cleaned.replace("```", "").strip()


# ── Structured call (with Pydantic validation) ────────────────────────────────

def call_llm_structured(
    prompt: str,
    model: str,
    output_schema: Type[T],
    system: str = "You are a precise assistant. Return ONLY valid JSON. No preamble. No backticks.",
    max_tokens: int = 2048,
    purpose: str = "structured_call",
) -> T:
    """
    Makes an LLM call and parses + validates the response into a Pydantic model.

    Retries once with an error correction prompt if JSON/Pydantic validation fails.

    Args:
        prompt:        User message
        model:         Model name
        output_schema: Pydantic model class to parse into
        system:        System prompt
        max_tokens:    Max output tokens
        purpose:       Label for logging

    Returns:
        Validated Pydantic model instance

    Raises:
        LLMFailureException: If parsing/validation fails after correction retry
    """
    raw = call_llm(prompt, model=model, system=system, max_tokens=max_tokens, purpose=purpose)

    # Attempt 1
    try:
        return output_schema.model_validate(json.loads(_clean_json(raw)))
    except (json.JSONDecodeError, ValidationError) as e:
        validation_error = str(e)
        logger.warning(f"[{purpose}] Parse failed, sending correction")

    # Attempt 2 — correction prompt
    correction = (
        f"Your previous response was not valid JSON or did not match the schema.\n"
        f"Error: {validation_error}\n\nPrevious response:\n{raw}\n\nOriginal request:\n{prompt}\n\n"
        f"Return ONLY valid JSON matching the schema. No preamble. No backticks."
    )
    raw2 = call_llm(
        correction, model=model, system=system,
        max_tokens=max_tokens, purpose=f"{purpose}_correction",
    )
    try:
        return output_schema.model_validate(json.loads(_clean_json(raw2)))
    except (json.JSONDecodeError, ValidationError) as e:
        raise LLMFailureException(
            f"[{purpose}] Failed to parse {output_schema.__name__} after correction. "
            f"Error: {e}\nResponse: {raw2}"
        )


if __name__ == "__main__":
    # Smoke test — Anthropic only (Gemini needs network to Google)
    from pydantic import BaseModel as PM

    class Echo(PM):
        message: str
        count: int

    print("Testing Anthropic call...")
    try:
        result = call_llm_structured(
            prompt='Return JSON: {"message": "hello", "count": 42}',
            model=settings.model_score_fit,
            output_schema=Echo,
            purpose="smoke_test",
        )
        print(f"  Claude: {result}")
    except Exception as e:
        print(f"  Claude error: {e}")

    print("\nTesting Gemini call (requires network)...")
    try:
        result = call_llm_structured(
            prompt='Return JSON: {"message": "hello from gemini", "count": 7}',
            model=settings.model_parse_job,
            output_schema=Echo,
            purpose="smoke_test_gemini",
        )
        print(f"  Gemini: {result}")
    except Exception as e:
        print(f"  Gemini error (expected in sandbox): {e}")
