"""Deterministic outbound content scanner — a code-level policy backstop.

Generic and profile-agnostic: rules are loaded from an operator-supplied JSON
file (``platforms.<platform>.extra.outbound_policy_rules_file``), not
hardcoded here. This module has no Safia-specific knowledge — it's a small,
reusable rule engine any profile can opt into.

Purpose: an LLM's own judgment (e.g. following a confidentiality policy
document) is advisory — a sufficiently confused or manipulated turn can still
get it wrong. This scanner is the hard backstop: it inspects the actual text
about to be delivered and blocks it if it matches a defined secret pattern,
independent of what the model decided. Defense in depth, not a replacement
for the model's own judgment.

Rules file shape (JSON):
{
  "categories": [
    {
      "name": "passport_id",
      "pattern": "\\b[A-Z]{2}\\s?\\d{7}\\b"
    },
    {
      "name": "salary_figure",
      "pattern": "\\b\\d{1,3}(?:[ ,]\\d{3}){2,3}\\s*(UZS|so'm|сум)\\b",
      "proximity_keywords": ["oylik", "maosh", "ish haqi", "bonus"],
      "proximity_chars": 60
    },
    {
      "name": "security_keyword",
      "keywords": ["xavfsizlik kodi", "signalizatsiya kodi", "seyf kodi"]
    }
  ]
}

A category matches if:
  - "pattern" alone: the regex matches anywhere in the text.
  - "pattern" + "proximity_keywords": the regex matches AND at least one
    proximity keyword appears within proximity_chars of the match.
  - "keywords" (no pattern): any keyword appears verbatim (case-insensitive).
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional


def load_policy_rules(path: str) -> Optional[dict]:
    """Load and parse a rules file. Returns None on any failure — a missing
    or broken rules file must degrade to "scanning disabled", never crash
    the message-delivery path."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("categories"), list):
        return None
    return data


def scan_text(text: str, rules: dict) -> Optional[dict]:
    """Scan text against loaded rules. Returns the first matching category's
    info dict ({"name": ..., "matched": ...}) or None if nothing matched."""
    if not text:
        return None
    lower_text = text.lower()

    for category in rules.get("categories", []):
        if not isinstance(category, dict):
            continue
        name = category.get("name", "unnamed")

        keywords = category.get("keywords")
        if keywords:
            for kw in keywords:
                if str(kw).lower() in lower_text:
                    return {"name": name, "matched": kw}
            continue

        pattern = category.get("pattern")
        if not pattern:
            continue
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error:
            continue

        proximity_keywords = category.get("proximity_keywords")
        proximity_chars = int(category.get("proximity_chars", 60))

        for m in compiled.finditer(text):
            if not proximity_keywords:
                return {"name": name, "matched": m.group(0)}
            window_start = max(0, m.start() - proximity_chars)
            window_end = min(len(text), m.end() + proximity_chars)
            window = text[window_start:window_end].lower()
            for kw in proximity_keywords:
                if str(kw).lower() in window:
                    return {"name": name, "matched": m.group(0), "context_keyword": kw}

    return None
