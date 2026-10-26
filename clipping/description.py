"""Description and CTA generator for clip posting.

Generates post captions and CTA categories per PRD-GROWTH sections 19-20.

Structure:
  Hook
  ↓
  short context  
  ↓
  optional CTA

CTA categories: follow, comment, save, share, profile, none

Do not spam CTA on every post.
Never use fake scarcity or misleading statements.
"""

import re
from typing import Dict, Optional


CTA_CATEGORIES = ["follow", "comment", "save", "share", "profile", "none"]


def _extract_hook(text: str, max_words: int = 8) -> str:
    """Extract the hook sentence (first complete sentence or first 8 words)."""
    if not text:
        return ""

    # Take first sentence
    sentences = re.findall(r"[^.!?。!?]+[.!?。!?]+", text)
    if sentences:
        first = sentences[0].strip()
        words = first.split()[:max_words]
        return " ".join(words)

    # Fallback: first words
    words = text.split()[:max_words]
    return " ".join(words)


def _extract_context(text: str, max_words: int = 40) -> str:
    """Extract short context after the hook."""
    if not text:
        return ""

    # Remove the hook (first sentence) and take remaining words
    sentences = re.findall(r"[^.!?。!?]+[.!?。!?]+", text)
    if len(sentences) >= 2:
        # Context is everything after the first sentence
        context_text = " ".join(sentences[1:])
    else:
        context_text = text

    words = context_text.split()[:max_words]
    return " ".join(words)


def _select_cta(
    exploration: bool = False,
    default_category: str = "none",
    account_has_data: bool = False,
) -> str:
    """Select a CTA category.

    80% proven patterns, 20% experiments (configurable ratio).
    When account has historical data, prefer proven categories.
    When no data and exploring, can use non-default CTAs.
    """
    if exploration and not account_has_data:
        # During exploration, rotate through categories
        import random
        # Weight: follow > comment > save > share > profile > none
        weights = [0.30, 0.20, 0.15, 0.15, 0.10, 0.10]
        choice = random.choices(CTA_CATEGORIES, weights=weights, k=1)[0]
        return choice

    # Default: no CTA or the default category
    return default_category


def generate_description(
    hook_text: str,
    context_text: str,
    *,
    exploration: bool = False,
    default_cta: str = "none",
    account_has_data: bool = False,
) -> Dict:
    """Generate a post description/caption per PRD-GROWTH §19.

    Structure: Hook + context + optional CTA

    Returns dict with: description, cta, cta_category
    """
    hook = _extract_hook(hook_text, max_words=8)
    context = _extract_context(context_text, max_words=40)
    cta_category = _select_cta(
        exploration=exploration,
        default_category=default_cta,
        account_has_data=account_has_data,
    )
    cta_text = _cta_text(cta_category)

    # Build description: hook + " " + context. If context is empty, just hook.
    description_parts = [hook] if hook else []
    if context:
        description_parts.append(context)

    description = " ".join(description_parts).strip()

    # If description is too short (just hook), that's fine - don't pad
    # If context was available but got truncated, we still include what we have

    return {
        "description": description,
        "cta": cta_text,
        "cta_category": cta_category,
    }


def _cta_text(category: str) -> str:
    """Generate the actual CTA phrase for a category."""
    cta_map = {
        "follow": "Follow for more breakdowns.",
        "comment": "Would you agree?",
        "save": "Save this for later.",
        "share": "Part 2 on profile.",
        "profile": "Check my profile for more.",
        "none": "",
    }
    return cta_map.get(category, "")


def generate_cta_only(category: Optional[str] = None) -> str:
    """Generate just the CTA phrase."""
    if category and category in CTA_CATEGORIES:
        return _cta_text(category)
    return _cta_text("none")