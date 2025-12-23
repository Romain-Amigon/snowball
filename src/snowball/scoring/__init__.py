"""Relevance scoring module for papers."""

from .base import BaseScorer
from .tfidf_scorer import TFIDFScorer

__all__ = ["BaseScorer", "TFIDFScorer", "get_scorer"]


def get_scorer(method: str = "tfidf", **kwargs) -> BaseScorer:
    """Factory function to get a scorer instance.

    Args:
        method: Scoring method - "tfidf" or "llm"
        **kwargs: Additional arguments for the scorer (e.g., api_key, model for LLM)

    Returns:
        Scorer instance

    Raises:
        ValueError: If method is unknown
        ImportError: If required dependencies are missing
    """
    if method == "tfidf":
        return TFIDFScorer()
    elif method == "llm":
        from .llm_scorer import LLMScorer

        return LLMScorer(**kwargs)
    else:
        raise ValueError(f"Unknown scoring method: {method}. Use 'tfidf' or 'llm'")
