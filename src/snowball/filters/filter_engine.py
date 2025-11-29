"""Filtering engine for papers."""

import logging
from typing import List
from ..models import Paper, FilterCriteria

logger = logging.getLogger(__name__)


class FilterEngine:
    """Engine for filtering papers based on criteria."""

    def apply_filters(self, papers: List[Paper], criteria: FilterCriteria) -> List[Paper]:
        """Apply filter criteria to a list of papers.

        Args:
            papers: List of papers to filter
            criteria: Filter criteria

        Returns:
            List of papers that pass all filters
        """
        filtered = papers

        # Apply year filters
        if criteria.min_year is not None:
            filtered = [p for p in filtered if self._check_min_year(p, criteria.min_year)]
            logger.debug(f"After min_year filter: {len(filtered)} papers")

        if criteria.max_year is not None:
            filtered = [p for p in filtered if self._check_max_year(p, criteria.max_year)]
            logger.debug(f"After max_year filter: {len(filtered)} papers")

        # Apply citation filters
        if criteria.min_citations is not None:
            filtered = [p for p in filtered if self._check_min_citations(p, criteria.min_citations)]
            logger.debug(f"After min_citations filter: {len(filtered)} papers")

        if criteria.max_citations is not None:
            filtered = [p for p in filtered if self._check_max_citations(p, criteria.max_citations)]
            logger.debug(f"After max_citations filter: {len(filtered)} papers")

        # Apply influential citation filter
        if criteria.min_influential_citations is not None:
            filtered = [
                p for p in filtered
                if self._check_min_influential_citations(p, criteria.min_influential_citations)
            ]
            logger.debug(f"After influential citations filter: {len(filtered)} papers")

        # Apply keyword filters
        if criteria.keywords:
            filtered = [p for p in filtered if self._check_keywords(p, criteria.keywords)]
            logger.debug(f"After keyword filter: {len(filtered)} papers")

        if criteria.excluded_keywords:
            filtered = [
                p for p in filtered
                if not self._check_keywords(p, criteria.excluded_keywords)
            ]
            logger.debug(f"After excluded keyword filter: {len(filtered)} papers")

        # Apply venue type filter
        if criteria.venue_types:
            filtered = [p for p in filtered if self._check_venue_type(p, criteria.venue_types)]
            logger.debug(f"After venue type filter: {len(filtered)} papers")

        logger.info(f"Filtered {len(papers)} papers down to {len(filtered)}")
        return filtered

    def _check_min_year(self, paper: Paper, min_year: int) -> bool:
        """Check if paper meets minimum year requirement."""
        if paper.year is None:
            # Include papers with unknown year (can be reviewed manually)
            return True
        return paper.year >= min_year

    def _check_max_year(self, paper: Paper, max_year: int) -> bool:
        """Check if paper meets maximum year requirement."""
        if paper.year is None:
            return True
        return paper.year <= max_year

    def _check_min_citations(self, paper: Paper, min_citations: int) -> bool:
        """Check if paper meets minimum citation count."""
        if paper.citation_count is None:
            # Include papers with unknown citation count
            return True
        return paper.citation_count >= min_citations

    def _check_max_citations(self, paper: Paper, max_citations: int) -> bool:
        """Check if paper meets maximum citation count."""
        if paper.citation_count is None:
            return True
        return paper.citation_count <= max_citations

    def _check_min_influential_citations(self, paper: Paper, min_count: int) -> bool:
        """Check if paper meets minimum influential citation count."""
        if paper.influential_citation_count is None:
            return True
        return paper.influential_citation_count >= min_count

    def _check_keywords(self, paper: Paper, keywords: List[str]) -> bool:
        """Check if paper contains any of the keywords.

        Searches in title and abstract.
        """
        # Create searchable text
        text_parts = []
        if paper.title:
            text_parts.append(paper.title.lower())
        if paper.abstract:
            text_parts.append(paper.abstract.lower())

        if not text_parts:
            # If no text to search, include the paper
            return True

        searchable_text = " ".join(text_parts)

        # Check if any keyword is present
        for keyword in keywords:
            if keyword.lower() in searchable_text:
                return True

        return False

    def _check_venue_type(self, paper: Paper, venue_types: List[str]) -> bool:
        """Check if paper is from one of the specified venue types."""
        if not paper.venue or not paper.venue.type:
            # Include papers with unknown venue
            return True

        venue_type = paper.venue.type.lower()

        # Normalize venue types
        normalized_types = [vt.lower() for vt in venue_types]

        # Check for matches (including partial matches)
        for vt in normalized_types:
            if vt in venue_type or venue_type in vt:
                return True

        return False

    def estimate_venue_quality(self, paper: Paper) -> str:
        """Estimate venue quality based on heuristics.

        Returns:
            Quality estimate: "high", "medium", "low", or "unknown"
        """
        # This is a basic heuristic - could be improved with venue ranking data
        if not paper.venue:
            return "unknown"

        # Use citation count as a proxy for quality
        if paper.citation_count is None:
            return "unknown"

        # Simple thresholds (these could be made configurable)
        if paper.citation_count >= 100:
            return "high"
        elif paper.citation_count >= 20:
            return "medium"
        else:
            return "low"
