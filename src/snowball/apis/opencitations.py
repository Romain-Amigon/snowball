"""OpenCitations API client for open citation data."""

import logging
import time
from typing import Optional, List, Dict, Any
import httpx

from .base import BaseAPIClient, RateLimitError, APINotFoundError
from ..models import Paper, Author, PaperSource
from ..storage.json_storage import JSONStorage

logger = logging.getLogger(__name__)


class OpenCitationsClient(BaseAPIClient):
    """Client for OpenCitations API.

    OpenCitations provides open bibliographic and citation data.
    API docs: https://opencitations.net/index/api/v2
    """

    BASE_URL = "https://opencitations.net/index/api/v2"

    def __init__(
        self,
        access_token: Optional[str] = None,
        rate_limit_delay: float = 0.1,
    ):
        """Initialize OpenCitations client.

        Args:
            access_token: OpenCitations access token (optional but recommended)
            rate_limit_delay: Delay between requests in seconds
        """
        self.rate_limit_delay = rate_limit_delay
        self.client = httpx.Client(timeout=30.0)

        # Set headers
        self.client.headers["User-Agent"] = "SnowballSLR/0.1"
        if access_token:
            self.client.headers["Authorization"] = access_token

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Make a request to the OpenCitations API.

        Returns list since OpenCitations returns arrays.
        """
        url = f"{self.BASE_URL}/{endpoint}"

        try:
            time.sleep(self.rate_limit_delay)
            response = self.client.get(url, params=params)

            if response.status_code == 429:
                raise RateLimitError("OpenCitations rate limit exceeded")
            elif response.status_code == 404:
                raise APINotFoundError(f"Resource not found: {endpoint}")
            elif response.status_code != 200:
                logger.error(f"OpenCitations API error: {response.status_code}")
                return []

            return response.json()

        except httpx.TimeoutException:
            logger.warning(f"Timeout requesting {url}")
            return []

    def _parse_metadata(self, data: Dict[str, Any], source: PaperSource = PaperSource.SEED) -> Paper:
        """Parse OpenCitations metadata response into a Paper object."""
        # Extract DOI (format: "doi:10.xxxx/yyyy")
        doi_raw = data.get("doi", "")
        doi = doi_raw.replace("doi:", "") if doi_raw else None

        # Extract title
        title = data.get("title", "Unknown Title")

        # Extract authors (format: "Family, Given; Family2, Given2")
        authors = []
        author_str = data.get("author", "")
        if author_str:
            for author_part in author_str.split(";"):
                author_part = author_part.strip()
                if author_part:
                    # Convert "Family, Given" to "Given Family"
                    if "," in author_part:
                        parts = author_part.split(",", 1)
                        name = f"{parts[1].strip()} {parts[0].strip()}"
                    else:
                        name = author_part
                    authors.append(Author(name=name))

        # Extract year (format: "2020-01-15" or "2020")
        year = None
        year_str = data.get("year", "")
        if year_str:
            try:
                year = int(year_str.split("-")[0])
            except (ValueError, IndexError):
                pass

        # Extract citation count
        citation_count = None
        citation_str = data.get("citation_count", "")
        if citation_str:
            try:
                citation_count = int(citation_str)
            except ValueError:
                pass

        # Create paper
        paper = Paper(
            id=JSONStorage.generate_id(),
            doi=doi,
            title=title,
            authors=authors,
            year=year,
            citation_count=citation_count,
            source=source,
            raw_data={"opencitations": data}
        )

        return paper

    def _parse_citation_record(self, data: Dict[str, Any], is_citing: bool = True) -> Optional[Paper]:
        """Parse a citation/reference record into a Paper object.

        Args:
            data: Citation record from API
            is_citing: If True, extract the citing paper; if False, extract the cited paper
        """
        # The record contains "citing" and "cited" DOIs
        doi_field = "citing" if is_citing else "cited"
        doi_raw = data.get(doi_field, "")

        if not doi_raw:
            return None

        # Clean DOI (format: "doi:10.xxxx/yyyy")
        doi = doi_raw.replace("doi:", "") if doi_raw.startswith("doi:") else doi_raw

        # OpenCitations citation records don't include full metadata
        # We create a minimal paper that can be enriched later
        paper = Paper(
            id=JSONStorage.generate_id(),
            doi=doi,
            title=f"Paper {doi}",  # Placeholder, will be enriched
            authors=[],
            source=PaperSource.CITATION if is_citing else PaperSource.REFERENCE,
            raw_data={"opencitations_citation": data}
        )

        return paper

    def search_by_doi(self, doi: str) -> Optional[Paper]:
        """Search for a paper by DOI using metadata endpoint."""
        try:
            # OpenCitations metadata endpoint accepts DOI format
            data = self._make_request(f"metadata/doi:{doi}")

            if data and len(data) > 0:
                return self._parse_metadata(data[0])

        except APINotFoundError:
            logger.debug(f"OpenCitations: Paper not found for DOI: {doi}")
        except Exception as e:
            logger.error(f"OpenCitations error searching by DOI {doi}: {e}")

        return None

    def search_by_title(self, title: str) -> Optional[Paper]:
        """Search for a paper by title.

        Note: OpenCitations doesn't support title search directly.
        """
        logger.debug("OpenCitations doesn't support title search")
        return None

    def get_references(self, doi: str) -> List[Paper]:
        """Get papers referenced by this paper (backward snowballing).

        Args:
            doi: DOI of the paper (without 'doi:' prefix)

        Returns:
            List of referenced papers (with DOIs only, need enrichment)
        """
        papers = []

        try:
            data = self._make_request(f"references/doi:{doi}")

            for record in data:
                paper = self._parse_citation_record(record, is_citing=False)
                if paper and paper.doi:
                    papers.append(paper)

            if papers:
                logger.info(f"OpenCitations: Found {len(papers)} references for {doi}")

        except APINotFoundError:
            logger.debug(f"OpenCitations: No references found for DOI: {doi}")
        except Exception as e:
            logger.error(f"OpenCitations error getting references for {doi}: {e}")

        return papers

    def get_citations(self, doi: str) -> List[Paper]:
        """Get papers citing this paper (forward snowballing).

        Args:
            doi: DOI of the paper (without 'doi:' prefix)

        Returns:
            List of citing papers (with DOIs only, need enrichment)
        """
        papers = []

        try:
            data = self._make_request(f"citations/doi:{doi}")

            for record in data:
                paper = self._parse_citation_record(record, is_citing=True)
                if paper and paper.doi:
                    papers.append(paper)

            if papers:
                logger.info(f"OpenCitations: Found {len(papers)} citations for {doi}")

        except APINotFoundError:
            logger.debug(f"OpenCitations: No citations found for DOI: {doi}")
        except Exception as e:
            logger.error(f"OpenCitations error getting citations for {doi}: {e}")

        return papers

    def get_citation_count(self, doi: str) -> Optional[int]:
        """Get citation count for a paper.

        Args:
            doi: DOI of the paper

        Returns:
            Citation count or None if not found
        """
        try:
            data = self._make_request(f"citation-count/doi:{doi}")

            if data and len(data) > 0:
                count_str = data[0].get("count", "")
                if count_str:
                    return int(count_str)

        except Exception as e:
            logger.debug(f"OpenCitations: Could not get citation count for {doi}: {e}")

        return None

    def enrich_metadata(self, paper: Paper) -> Paper:
        """Enrich paper metadata using OpenCitations."""
        if not paper.doi:
            return paper

        oc_paper = self.search_by_doi(paper.doi)

        if oc_paper:
            # Merge data - only fill in missing fields
            if not paper.title or paper.title == "Unknown Title" or paper.title.startswith("Paper "):
                paper.title = oc_paper.title
            if not paper.year:
                paper.year = oc_paper.year
            if not paper.authors:
                paper.authors = oc_paper.authors

            # Update citation count if we have a better value
            if oc_paper.citation_count and (not paper.citation_count or oc_paper.citation_count > paper.citation_count):
                paper.citation_count = oc_paper.citation_count

            # Merge raw data
            if paper.raw_data is None:
                paper.raw_data = {}
            paper.raw_data.update(oc_paper.raw_data)

        return paper

    def __del__(self):
        """Close the HTTP client."""
        if hasattr(self, 'client'):
            self.client.close()
