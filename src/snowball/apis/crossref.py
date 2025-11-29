"""CrossRef API client."""

import logging
import time
from typing import Optional, List, Dict, Any
import httpx

from .base import BaseAPIClient, RateLimitError, APINotFoundError
from ..models import Paper, Author, Venue, PaperSource
from ..storage.json_storage import JSONStorage

logger = logging.getLogger(__name__)


class CrossRefClient(BaseAPIClient):
    """Client for CrossRef API."""

    BASE_URL = "https://api.crossref.org"

    def __init__(self, email: Optional[str] = None, rate_limit_delay: float = 0.05):
        """Initialize CrossRef client.

        Args:
            email: Email for polite pool (higher rate limits)
            rate_limit_delay: Delay between requests in seconds
        """
        self.rate_limit_delay = rate_limit_delay
        self.client = httpx.Client(timeout=30.0)

        # Use polite pool if email provided
        if email:
            self.client.headers["User-Agent"] = f"SnowballSLR/0.1 (mailto:{email})"

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make a request to the CrossRef API."""
        url = f"{self.BASE_URL}/{endpoint}"

        try:
            time.sleep(self.rate_limit_delay)
            response = self.client.get(url, params=params)

            if response.status_code == 429:
                raise RateLimitError("CrossRef rate limit exceeded")
            elif response.status_code == 404:
                raise APINotFoundError(f"Resource not found: {endpoint}")
            elif response.status_code != 200:
                logger.error(f"API error: {response.status_code}")
                return {}

            return response.json()

        except httpx.TimeoutException:
            logger.warning(f"Timeout requesting {url}")
            return {}

    def _parse_paper(self, data: Dict[str, Any], source: PaperSource = PaperSource.SEED) -> Paper:
        """Parse CrossRef API response into a Paper object."""
        # Extract DOI
        doi = data.get("DOI")

        # Extract title
        title_list = data.get("title", [])
        title = title_list[0] if title_list else "Unknown Title"

        # Extract authors
        authors = []
        for author_data in data.get("author", []):
            given = author_data.get("given", "")
            family = author_data.get("family", "")
            name = f"{given} {family}".strip()
            if name:
                authors.append(Author(name=name))

        # Extract year
        year = None
        date_parts = data.get("published", {}).get("date-parts")
        if date_parts and date_parts[0]:
            year = date_parts[0][0]

        # Extract venue
        venue = None
        container_title = data.get("container-title")
        if container_title:
            venue_name = container_title[0] if isinstance(container_title, list) else container_title
            venue = Venue(
                name=venue_name,
                year=year,
                type=data.get("type"),
                volume=data.get("volume"),
                issue=data.get("issue"),
                pages=data.get("page")
            )

        # Extract abstract (not always available)
        abstract = data.get("abstract")

        # Create paper
        paper = Paper(
            id=JSONStorage.generate_id(),
            doi=doi,
            title=title,
            authors=authors,
            year=year,
            abstract=abstract,
            venue=venue,
            citation_count=data.get("is-referenced-by-count"),
            source=source,
            raw_data={"crossref": data}
        )

        return paper

    def search_by_doi(self, doi: str) -> Optional[Paper]:
        """Search for a paper by DOI."""
        try:
            data = self._make_request(f"works/{doi}")

            if data and "message" in data:
                return self._parse_paper(data["message"])

        except APINotFoundError:
            logger.info(f"Paper not found for DOI: {doi}")
        except Exception as e:
            logger.error(f"Error searching by DOI {doi}: {e}")

        return None

    def search_by_title(self, title: str) -> Optional[Paper]:
        """Search for a paper by title."""
        try:
            data = self._make_request(
                "works",
                params={
                    "query.title": title,
                    "rows": 1
                }
            )

            if data and "message" in data and "items" in data["message"]:
                items = data["message"]["items"]
                if items:
                    return self._parse_paper(items[0])

        except Exception as e:
            logger.error(f"Error searching by title '{title}': {e}")

        return None

    def get_references(self, paper_id: str) -> List[Paper]:
        """Get papers referenced by this paper.

        Note: CrossRef has limited reference data.
        """
        # CrossRef doesn't provide comprehensive reference data
        # This would require parsing the paper itself
        logger.info("CrossRef doesn't provide comprehensive reference data")
        return []

    def get_citations(self, paper_id: str) -> List[Paper]:
        """Get papers citing this paper.

        Note: CrossRef provides citation counts but not full citation lists.
        """
        # CrossRef provides citation counts but not lists of citing papers
        logger.info("CrossRef doesn't provide citation lists, only counts")
        return []

    def enrich_metadata(self, paper: Paper) -> Paper:
        """Enrich paper metadata using CrossRef."""
        cr_paper = None

        if paper.doi:
            cr_paper = self.search_by_doi(paper.doi)
        elif paper.title:
            cr_paper = self.search_by_title(paper.title)

        if cr_paper:
            # Merge data
            if not paper.title or paper.title == "Unknown Title":
                paper.title = cr_paper.title
            if not paper.abstract:
                paper.abstract = cr_paper.abstract
            if not paper.year:
                paper.year = cr_paper.year
            if not paper.authors:
                paper.authors = cr_paper.authors
            if not paper.venue:
                paper.venue = cr_paper.venue
            if not paper.doi:
                paper.doi = cr_paper.doi

            # Update citation count if not set
            if not paper.citation_count and cr_paper.citation_count:
                paper.citation_count = cr_paper.citation_count

            # Merge raw data
            paper.raw_data.update(cr_paper.raw_data)

        return paper

    def __del__(self):
        """Close the HTTP client."""
        self.client.close()
