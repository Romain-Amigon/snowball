"""Base API client interface."""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from ..models import Paper, Author, Venue


class BaseAPIClient(ABC):
    """Abstract base class for academic API clients."""

    @abstractmethod
    def search_by_doi(self, doi: str) -> Optional[Paper]:
        """Search for a paper by DOI.

        Args:
            doi: Digital Object Identifier

        Returns:
            Paper object if found, None otherwise
        """
        pass

    @abstractmethod
    def search_by_title(self, title: str) -> Optional[Paper]:
        """Search for a paper by title.

        Args:
            title: Paper title

        Returns:
            Paper object if found, None otherwise
        """
        pass

    @abstractmethod
    def get_references(self, paper_id: str) -> List[Paper]:
        """Get papers referenced by this paper (backward snowballing).

        Args:
            paper_id: API-specific paper identifier

        Returns:
            List of referenced papers
        """
        pass

    @abstractmethod
    def get_citations(self, paper_id: str) -> List[Paper]:
        """Get papers citing this paper (forward snowballing).

        Args:
            paper_id: API-specific paper identifier

        Returns:
            List of citing papers
        """
        pass

    @abstractmethod
    def enrich_metadata(self, paper: Paper) -> Paper:
        """Enrich paper metadata using this API.

        Args:
            paper: Paper with partial information

        Returns:
            Paper with enriched metadata
        """
        pass


class APIClientError(Exception):
    """Base exception for API client errors."""
    pass


class RateLimitError(APIClientError):
    """Raised when API rate limit is exceeded."""
    pass


class APINotFoundError(APIClientError):
    """Raised when resource is not found."""
    pass
