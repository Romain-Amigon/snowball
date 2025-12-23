"""Base class for relevance scoring methods."""

from abc import ABC, abstractmethod
from typing import List, Optional, Callable, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import Paper


class BaseScorer(ABC):
    """Abstract base class for relevance scoring."""

    @abstractmethod
    def score_papers(
        self,
        research_question: str,
        papers: List["Paper"],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Tuple["Paper", float]]:
        """Score papers against research question.

        Args:
            research_question: The research question to compare against
            papers: List of papers to score
            progress_callback: Optional callback(current, total) for progress updates

        Returns:
            List of (paper, score) tuples where score is 0.0-1.0
        """
        pass

    @staticmethod
    def get_paper_text(paper: "Paper") -> str:
        """Get searchable text from paper (title + abstract).

        Args:
            paper: Paper to extract text from

        Returns:
            Combined title and abstract text
        """
        parts = []
        if paper.title:
            parts.append(paper.title)
        if paper.abstract:
            parts.append(paper.abstract)
        return " ".join(parts)
