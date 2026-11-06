"""Keyword rules: used when no trained classifier is available, and as an eval baseline.

They guess a task category and a complexity level from words in the prompt.
They do not produce probabilities, so the router picks a model tier directly.
"""

import re

CATEGORY_KEYWORDS = {
    "coding": [
        "code", "function", "bug", "debug", "error", "exception", "traceback", "python", "javascript",
        "java", "sql", "regex", "api", "class ", "compile", "refactor", "unit test", "script", "```",
    ],
    "math": ["prove", "solve", "equation", "calculate", "probability", "integral", "derivative", "math", "how many"],
    "summarization": ["summarize", "summarise", "summary", "tl;dr", "tldr", "key points", "condense", "shorten"],
    "extraction": ["extract", "list all", "pull out", "parse", "json", "table of", "find all", "fields"],
    "writing": ["write", "draft", "email", "essay", "poem", "story", "rewrite", "cover letter", "blog", "tweet"],
}

HARD_SIGNALS = [
    "prove", "optimize", "optimise", "architecture", "race condition", "concurrency", "deadlock",
    "algorithm", "complexity", "step by step", "trade-off", "tradeoff", "design a", "distributed",
]


def detect_category(prompt):
    text = prompt.lower()
    best, best_hits = "chat", 0
    for category, words in CATEGORY_KEYWORDS.items():
        hits = sum(1 for w in words if w in text)
        if hits > best_hits:
            best, best_hits = category, hits
    return best


def estimate_complexity(prompt):
    """Return "low", "medium" or "high" from length, code and hard-task words."""
    text = prompt.lower()
    has_code = "```" in prompt or bool(re.search(r"\b(def|class|return|import|SELECT|function)\b", prompt))
    hard_hits = sum(1 for w in HARD_SIGNALS if w in text)
    if hard_hits >= 1 or (has_code and len(prompt) > 400) or len(prompt) > 2000:
        return "high"
    if len(prompt) < 120 and not has_code and detect_category(prompt) == "chat":
        return "low"
    return "medium"


COMPLEXITY_TO_TIER = {"low": 1, "medium": 2, "high": 3}


def target_tier(prompt, priority):
    """Model tier (1 small, 2 medium, 3 large) the keyword rules would pick."""
    tier = COMPLEXITY_TO_TIER[estimate_complexity(prompt)]
    if priority in ("cheapest", "fastest"):
        tier = max(1, tier - 1)
    elif priority == "quality":
        tier = 3
    return tier
