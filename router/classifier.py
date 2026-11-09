"""The trained part of the router.

A small Hugging Face embedding model turns each prompt into 384 numbers. For each
LLM, a logistic regression trained on the judged benchmark turns those numbers
into P(this model gives a good answer). A second logistic regression predicts the
task category, which is used for explanations, rules and feedback.

train_router writes the artifact; this module only loads it and predicts.
"""

import logging
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

_embedder = None
_artifact_cache = {"key": None, "artifact": None}


def embed(texts):
    """Return an array of shape (len(texts), 384). Loads the embedder on first use."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        _embedder = SentenceTransformer(settings.ROUTER_EMBEDDER, device="cpu")
    text_list = [t[: settings.ROUTER_CLASSIFIER_MAX_CHARS] for t in texts]
    return _embedder.encode(text_list, normalize_embeddings=True, show_progress_bar=False)


def load_artifact():
    """The trained artifact dict, or None if it is missing or unreadable."""
    path = Path(settings.ROUTER_ARTIFACT_PATH)
    if not path.exists():
        return None
    key = (str(path), path.stat().st_mtime)
    if _artifact_cache["key"] != key:
        try:
            import joblib

            _artifact_cache["artifact"] = joblib.load(path)
        except Exception:
            logger.exception("Could not load router artifact %s", path)
            _artifact_cache["artifact"] = None
        _artifact_cache["key"] = key
    return _artifact_cache["artifact"]


def model_probability(entry, vectors):
    """P(good) for each row of vectors from one per-model entry of the artifact."""
    if entry["kind"] == "constant":
        return [entry["p"]] * len(vectors)
    return list(entry["clf"].predict_proba(vectors)[:, 1])


def predict(prompt):
    """Return {"p_good": {model_id: p}, "category": str} or None when unavailable."""
    artifact = load_artifact()
    if artifact is None:
        return None
    try:
        vectors = embed([prompt])
        p_good = {model_id: float(model_probability(entry, vectors)[0]) for model_id, entry in artifact["models"].items()}
        category = str(artifact["category_clf"].predict(vectors)[0])
    except Exception:
        logger.exception("Router classifier failed; falling back to keyword rules")
        return None
    return {"p_good": p_good, "category": category}
