"""
Structured logging for AI Job Copilot.
Consistent format across all modules.
"""

import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """Returns a configured logger for the given module name."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def log_llm_call(
    logger: logging.Logger,
    model: str,
    tokens_in: int,
    tokens_out: int,
    duration_ms: float,
    purpose: str,
    cost: float = 0.0,
) -> None:
    """
    Logs every LLM call with provider, token usage, cost, and duration.

    Args:
        logger:      Logger instance
        model:       Full model name
        tokens_in:   Input token count
        tokens_out:  Output token count
        duration_ms: Request duration in milliseconds
        purpose:     Label e.g. 'parse_job', 'score_fit'
        cost:        Pre-computed USD cost (from llm.py per provider rates)
    """
    provider = "gemini" if model.startswith("gemini") else "claude"
    # Short label: "gemini/flash" or "claude/sonnet"
    parts = model.split("-")
    short = parts[1] if len(parts) > 1 else model
    logger.info(
        f"[LLM:{purpose}] {provider}/{short} "
        f"in={tokens_in} out={tokens_out} "
        f"cost=${cost:.5f} "
        f"duration={duration_ms:.0f}ms"
    )


if __name__ == "__main__":
    log = get_logger("test")
    log.info("Logger working correctly")
    log_llm_call(log, "claude-sonnet-4-20250514", 1200, 400, 1850.0, "test_call", cost=0.00968)
    log_llm_call(log, "gemini-2.5-flash-preview-04-17", 3000, 800, 620.0, "test_gemini", cost=0.00093)
