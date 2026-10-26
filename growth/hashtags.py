"""Niche-aware hashtag candidates with transparent per-tag scores."""

import re
from collections.abc import Iterable

_WORD = re.compile(r"[a-z][a-z0-9]{2,}")
_STOP = {"the", "and", "for", "with", "from", "then", "was", "are", "this", "that", "into", "your", "you", "how", "what", "when", "about", "good", "day", "strategy", "thing", "things"}
_DISCOVERY = {
    "business": ("entrepreneurship", "smallbusiness", "businessgrowth"),
    "podcast": ("podcastclips", "longformcontent", "conversation"),
    "gaming": ("gamingclips", "gameplay", "videogames"),
    "technology": ("technews", "innovation", "digitaltools"),
    "sports": ("sportsclips", "sportsanalysis", "athlete"),
    "motivation": ("personalgrowth", "motivationdaily", "selfimprovement"),
}


def _words(values: Iterable[str] | str | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = re.split(r"[,;\s]+", values)
    elif isinstance(values, (set, frozenset)):
        values = sorted(values)
    result = []
    for value in values:
        result.extend(w for w in _WORD.findall(str(value).lower()) if w not in _STOP)
    return list(dict.fromkeys(result))


class HashtagGenerator:
    """Builds only tags supported by the supplied niche/topic evidence."""

    def __init__(self, niche_keywords=None, topic_keywords=None, account_history=None,
                 recent_posts=None, config=None):
        self.niche_keywords = _words(niche_keywords)
        self.topic_keywords = _words(topic_keywords)
        self.account_history = {str(k).lower().lstrip("#"): float(v) for k, v in (account_history or {}).items()}
        self.recent_posts = list(recent_posts or [])[-20:]
        self.config = {"min": 3, "preferred": 5, "max": 8, **(config or {})}

    def generate(self, clip_topic=None, account_handle=None, platform=None):
        context = _words(clip_topic)
        context_set = set(context)
        topic = list(dict.fromkeys(self.topic_keywords + [w for w in context if w not in self.niche_keywords]))
        niche = list(self.niche_keywords)
        discovery = []
        for key in niche:
            discovery.extend(_DISCOVERY.get(key, ()))
        candidates = []
        for layer, words in (("niche", niche), ("topic", topic), ("discovery", discovery)):
            for word in words:
                if word not in _STOP and (layer != "topic" or not context or word in context_set or word in self.topic_keywords):
                    candidates.append((f"#{word}", layer))
        # Stable unique candidates; retain their strongest first-layer assignment.
        unique = {}
        for tag, layer in candidates:
            unique.setdefault(tag, layer)
        scored = {}
        for tag, layer in unique.items():
            word = tag[1:]
            recent_count = sum(1 for post in self.recent_posts if re.search(rf"(?<!\w)#{re.escape(word)}(?!\w)", post, re.I))
            history = self.account_history.get(word, 0.5)
            relevance = 1.0 if word in self.topic_keywords else (0.9 if word in context_set else (0.8 if layer == "niche" else 0.4))
            scores = {"relevance": relevance, "account_history": max(0.0, min(1.0, history)),
                      "discoverability": 0.8 if layer == "niche" else (0.65 if layer == "topic" else 0.45),
                      "freshness": max(0.0, 1 - 0.25 * recent_count)}
            scores["total"] = round(scores["relevance"] * .45 + scores["account_history"] * .25 + scores["discoverability"] * .20 + scores["freshness"] * .10, 4)
            scored[tag] = scores
        # Alternate layers so a large niche keyword list cannot crowd out clip context.
        by_layer = {layer: [] for layer in ("niche", "topic", "discovery")}
        for tag, layer in unique.items():
            by_layer[layer].append(tag)
        for layer in by_layer:
            by_layer[layer].sort(key=lambda t: (scored[t]["total"], t), reverse=True)
        selected, breakdown = [], {layer: [] for layer in by_layer}
        # Keep niche and topic evidence ahead of broader discovery candidates.
        for layer in ("niche", "topic", "discovery"):
            while by_layer[layer] and len(selected) < int(self.config["preferred"]):
                tag = by_layer[layer].pop(0)
                selected.append(tag)
                breakdown[layer].append(tag)
        total = round(sum(scored[t]["total"] for t in selected) / len(selected), 4) if selected else 0.0
        minimum = int(self.config["min"])
        return {"hashtags": selected, "layer_breakdown": breakdown, "score": total, "scores": scored,
                "count": len(selected), "shortfall": max(0, minimum - len(selected)), "config": self.config,
                "platform": platform}

    def set_recent_posts(self, posts):
        self.recent_posts = list(posts)[-20:]

    def set_account_history(self, history):
        self.account_history = {str(k).lower().lstrip("#"): float(v) for k, v in history.items()}
