"""
Pydantic validation helpers and common parsing utilities.
"""

import hashlib
from typing import Any
from pydantic import ValidationError
from utils.logger import get_logger

logger = get_logger(__name__)


def hash_text(text: str) -> str:
    """
    Returns SHA256 hash of text — used for duplicate detection.

    Args:
        text: Raw text to hash

    Returns:
        Hex string SHA256 digest
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_validate(schema_class: Any, data: dict, context: str = "") -> Any | None:
    """
    Attempts Pydantic validation and logs on failure without crashing.
    For critical paths, use call_llm_structured which raises on failure.
    This is for non-critical optional parsing.

    Args:
        schema_class: Pydantic model class
        data: Dictionary to validate
        context: Label for error logging

    Returns:
        Validated model or None on failure
    """
    try:
        return schema_class.model_validate(data)
    except ValidationError as e:
        logger.error(f"[{context}] Validation failed: {e}")
        return None


def count_words(text: str) -> int:
    """
    Counts words in a string. Returns 0 for empty/whitespace-only strings.

    Args:
        text: Input string

    Returns:
        Word count
    """
    stripped = text.strip()
    if not stripped:
        return 0
    return len(stripped.split())


if __name__ == "__main__":
    test_hash = hash_text("Junior AI Engineer at Acme Corp...")
    print(f"✅ Hash: {test_hash[:16]}...")
    print(f"✅ Word count: {count_words('Hello world this is a test')}")
