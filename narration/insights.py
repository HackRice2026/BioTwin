"""Retrieval side of the precomputed model-analysis embeddings (see
scripts/generate_insights.py for the generation side). The coach otherwise has no way to
ground a question about forecast accuracy or the recovery model -- that analysis lives in
docs/Matlab.md and matlab/results/, never in NarrationContext. Rather than recomputing or
re-deriving anything live, a matching question gets the one relevant precomputed fact folded
into ctx.facts, the same free-text grounding slot modeling/explanations.py already fills."""

import math
import re

from narration.embeddings import embed_text

METHODOLOGY_QUESTION = re.compile(
    r"\b(matlab|model compar\w*|how accurate|accurac\w*|baseline\w*|trust (the |your )?forecast|"
    r"how (do|did) you (know|calculate|compute)|recovery (time|constant)|\btau\b|"
    r"boosted trees|bagged trees|ridge regression|gaussian process|validation error|"
    r"mean absolute error|\bmae\b)\b",
    re.I,
)


def wants_methodology_insight(question):
    return bool(METHODOLOGY_QUESTION.search(question))


def _cosine(a, b):
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


async def retrieve_insight(question, store, config, http, limit=1, threshold=0.6):
    """Returns up to `limit` precomputed fact strings relevant to `question`, or []
    when the question isn't methodology-flavored, embeddings are unavailable, or
    nothing stored clears the similarity threshold."""
    if not wants_methodology_insight(question):
        return []
    query_embedding = await embed_text(question, config, http)
    if not query_embedding:
        return []
    scored = sorted(
        (
            (_cosine(query_embedding, row["embedding"]), row["content"])
            for row in store.list_insights()
            if row.get("embedding")
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [content for score, content in scored[:limit] if score >= threshold]
