"""Punctuation rules for generated guard replies."""

import re


def guard_text(value: str) -> str:
    """Format generated prose without rewriting player messages or source documents."""
    value = re.sub(r"\s*[\u2012-\u2015]\s*", ". ", value)
    value = re.sub(r";\s*", ". ", value)
    return re.sub(r"([.!?]\s+)([a-z])", lambda match: match[1] + match[2].upper(), value).strip()
