"""Shared matching rules for title-only searches."""
from __future__ import annotations

import re


_ASCII_TOKEN = re.compile(r"^[a-z0-9_.+%_-]+$")


def title_matches(title: object, query: object) -> int:
    """Match every query term; ASCII terms start at a word boundary.

    Prefix matching keeps type-ahead useful (``ora`` -> ``Oracle``) while
    avoiding embedded false positives (``rac`` no longer matches ``Oracle``).
    CJK and mixed-language terms retain ordinary substring matching.
    """
    text = str(title or "").casefold()
    terms = str(query or "").strip().casefold().split()
    if not terms:
        return 1
    for term in terms:
        if _ASCII_TOKEN.fullmatch(term):
            if not re.search(rf"(?<![a-z]){re.escape(term)}", text):
                return 0
        elif term not in text:
            return 0
    return 1
