"""LLM-based relevance scoring using OpenAI API."""

import json
import logging
import os
from typing import List, Optional, Callable, Tuple, TYPE_CHECKING

from .base import BaseScorer

if TYPE_CHECKING:
    from ..models import Paper

logger = logging.getLogger(__name__)

# Batch size as recommended by owner (issue #25)
BATCH_SIZE = 20


class LLMScorer(BaseScorer):
    """Score papers using LLM assessment via OpenAI API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
    ):
        """Initialize LLM scorer.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Model to use for scoring (default: gpt-4o-mini for cost efficiency)
            base_url: Optional base URL for API (for OpenAI-compatible endpoints)
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self.base_url = base_url
        self._client = None

        if not self.api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter."
            )

    @property
    def client(self):
        """Lazy load OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI

                kwargs = {"api_key": self.api_key}
                if self.base_url:
                    kwargs["base_url"] = self.base_url

                self._client = OpenAI(**kwargs)
            except ImportError:
                raise ImportError(
                    "openai package required for LLM scoring. "
                    "Install with: pip install snowball-slr[llm]"
                )
        return self._client

    def score_papers(
        self,
        research_question: str,
        papers: List["Paper"],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Tuple["Paper", float]]:
        """Score papers using LLM assessment in batches."""
        if not papers:
            return []

        results = []
        total = len(papers)

        # Process in batches of BATCH_SIZE
        for batch_start in range(0, len(papers), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(papers))
            batch = papers[batch_start:batch_end]

            batch_scores = self._score_batch(research_question, batch)
            results.extend(batch_scores)

            if progress_callback:
                progress_callback(batch_end, total)

        return results

    def _score_batch(
        self,
        research_question: str,
        papers: List["Paper"],
    ) -> List[Tuple["Paper", float]]:
        """Score a batch of papers with a single API call."""
        # Build prompt with all papers in batch
        papers_text = []
        for i, paper in enumerate(papers):
            text = f"[{i + 1}] Title: {paper.title}\n"
            if paper.abstract:
                # Truncate long abstracts to save tokens
                abstract = (
                    paper.abstract[:1000] + "..."
                    if len(paper.abstract) > 1000
                    else paper.abstract
                )
                text += f"Abstract: {abstract}\n"
            papers_text.append(text)

        prompt = f"""You are assessing the relevance of academic papers to a research question.

Research Question: {research_question}

For each paper below, provide a relevance score from 0.0 to 1.0 where:
- 0.0 = Completely irrelevant
- 0.3 = Tangentially related
- 0.5 = Somewhat relevant
- 0.7 = Quite relevant
- 1.0 = Highly relevant to the research question

Papers to assess:
{chr(10).join(papers_text)}

Respond with ONLY a JSON array of numbers (the scores) in order, like: [0.7, 0.3, 0.9]
No explanation needed, just the scores array."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.1,  # Low temperature for consistency
            )

            # Parse response
            content = response.choices[0].message.content.strip()

            # Handle potential markdown code blocks
            if content.startswith("```"):
                # Extract content between code fences
                lines = content.split("\n")
                content = "\n".join(
                    line for line in lines if not line.startswith("```")
                ).strip()

            scores = json.loads(content)

            if len(scores) != len(papers):
                logger.warning(
                    f"LLM returned {len(scores)} scores for {len(papers)} papers"
                )
                # Pad or truncate
                while len(scores) < len(papers):
                    scores.append(0.0)
                scores = scores[: len(papers)]

            # Clamp scores to valid range
            scores = [max(0.0, min(1.0, float(s))) for s in scores]

            return [(paper, score) for paper, score in zip(papers, scores)]

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response content: {content}")
            return [(paper, 0.0) for paper in papers]
        except Exception as e:
            logger.error(f"LLM scoring failed: {e}")
            # Return 0.0 for all papers in batch on error
            return [(paper, 0.0) for paper in papers]
