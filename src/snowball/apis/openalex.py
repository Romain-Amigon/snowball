"""OpenAlex API client."""

import logging
import time
from typing import Optional, List, Dict, Any
import httpx

from .base import BaseAPIClient, RateLimitError, APINotFoundError
from ..models import Paper, Author, Venue, PaperSource
from ..storage.json_storage import JSONStorage

logger = logging.getLogger(__name__)


class OpenAlexClient(BaseAPIClient):
    """Client for OpenAlex API."""

    BASE_URL = "https://api.openalex.org"

    def __init__(self, email: Optional[str] = None, rate_limit_delay: float = 0.1):
        """Initialize OpenAlex client.

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
        """Make a request to the OpenAlex API."""
        url = f"{self.BASE_URL}/{endpoint}"

        try:
            time.sleep(self.rate_limit_delay)
            response = self.client.get(url, params=params)

            if response.status_code == 429:
                raise RateLimitError("OpenAlex rate limit exceeded")
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
        """Parse OpenAlex API response into a Paper object."""
        # Extract identifiers
        openalex_id = data.get("id", "").split("/")[-1]  # Get ID from URL
        doi = data.get("doi", "").replace("https://doi.org/", "") if data.get("doi") else None

        # Extract title
        title = data.get("title", "Unknown Title")

        # Extract authors
        authors = []
        for authorship in data.get("authorships", []):
            author_data = authorship.get("author", {})
            name = author_data.get("display_name")
            if name:
                # Get institutions
                affiliations = [
                    inst.get("display_name")
                    for inst in authorship.get("institutions", [])
                    if inst.get("display_name")
                ]
                authors.append(Author(name=name, affiliations=affiliations))

        # Extract year
        year = data.get("publication_year")

        # Extract abstract
        abstract_inverted_index = data.get("abstract_inverted_index")
        abstract = None
        if abstract_inverted_index:
            # Reconstruct abstract from inverted index
            abstract = self._reconstruct_abstract(abstract_inverted_index)

        # Extract venue
        venue = None
        primary_location = data.get("primary_location", {})
        source_data = primary_location.get("source")
        if source_data:
            venue = Venue(
                name=source_data.get("display_name"),
                type=source_data.get("type"),
                year=year
            )

        # Extract citation count
        citation_count = data.get("cited_by_count")

        # Create paper
        paper = Paper(
            id=JSONStorage.generate_id(),
            openalex_id=openalex_id,
            doi=doi,
            title=title,
            authors=authors,
            year=year,
            abstract=abstract,
            venue=venue,
            citation_count=citation_count,
            source=source,
            raw_data={"openalex": data}
        )

        return paper

    def _reconstruct_abstract(self, inverted_index: Dict[str, List[int]]) -> str:
        """Reconstruct abstract text from inverted index."""
        try:
            # Create a list to hold words at their positions
            max_pos = max(max(positions) for positions in inverted_index.values())
            words = [""] * (max_pos + 1)

            # Place each word at its positions
            for word, positions in inverted_index.items():
                for pos in positions:
                    words[pos] = word

            # Join words
            abstract = " ".join(words).strip()
            return abstract[:1000]  # Limit length
        except Exception as e:
            logger.warning(f"Error reconstructing abstract: {e}")
            return ""

    def search_by_doi(self, doi: str) -> Optional[Paper]:
        """Search for a paper by DOI."""
        try:
            # OpenAlex uses DOI URLs
            doi_url = f"https://doi.org/{doi}"
            data = self._make_request(
                "works",
                params={"filter": f"doi:{doi}"}
            )

            if data and "results" in data and data["results"]:
                return self._parse_paper(data["results"][0])

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
                    "search": title,
                    "per-page": 1
                }
            )

            if data and "results" in data and data["results"]:
                return self._parse_paper(data["results"][0])

        except Exception as e:
            logger.error(f"Error searching by title '{title}': {e}")

        return None

    def get_paper_by_id(self, openalex_id: str) -> Optional[Paper]:
        """Get a paper by OpenAlex ID."""
        try:
            # Ensure ID has proper format
            if not openalex_id.startswith("W"):
                openalex_id = f"W{openalex_id}"

            data = self._make_request(f"works/{openalex_id}")

            if data:
                return self._parse_paper(data)

        except APINotFoundError:
            logger.info(f"Paper not found for ID: {openalex_id}")
        except Exception as e:
            logger.error(f"Error getting paper {openalex_id}: {e}")

        return None

    def get_references(self, paper_id: str, limit: int = 1000) -> List[Paper]:
        """Get papers referenced by this paper."""
        references = []

        try:
            # Get the paper first to access referenced works
            paper_data = self._make_request(f"works/{paper_id}")

            if not paper_data:
                return references

            # Get referenced work IDs
            referenced_works = paper_data.get("referenced_works", [])

            # Fetch each referenced work (in batches to avoid too many requests)
            for ref_id in referenced_works[:limit]:
                ref_id = ref_id.split("/")[-1]  # Extract ID from URL
                ref_paper = self.get_paper_by_id(ref_id)
                if ref_paper:
                    ref_paper.source = PaperSource.BACKWARD
                    references.append(ref_paper)

        except Exception as e:
            logger.error(f"Error getting references for {paper_id}: {e}")

        logger.info(f"Found {len(references)} references for paper {paper_id}")
        return references

    def get_citations(self, paper_id: str, limit: int = 1000) -> List[Paper]:
        """Get papers citing this paper."""
        citations = []

        try:
            page = 1
            per_page = 100

            while len(citations) < limit:
                data = self._make_request(
                    "works",
                    params={
                        "filter": f"cites:{paper_id}",
                        "per-page": min(per_page, limit - len(citations)),
                        "page": page
                    }
                )

                if not data or "results" not in data or not data["results"]:
                    break

                for work in data["results"]:
                    paper = self._parse_paper(work, source=PaperSource.FORWARD)
                    citations.append(paper)

                # Check if there are more pages
                if len(data["results"]) < per_page:
                    break

                page += 1

        except Exception as e:
            logger.error(f"Error getting citations for {paper_id}: {e}")

        logger.info(f"Found {len(citations)} citations for paper {paper_id}")
        return citations

    def enrich_metadata(self, paper: Paper) -> Paper:
        """Enrich paper metadata using OpenAlex."""
        oa_paper = None

        if paper.openalex_id:
            oa_paper = self.get_paper_by_id(paper.openalex_id)
        elif paper.doi:
            oa_paper = self.search_by_doi(paper.doi)
        elif paper.title:
            oa_paper = self.search_by_title(paper.title)

        if oa_paper:
            # Merge data
            if not paper.title or paper.title == "Unknown Title":
                paper.title = oa_paper.title
            if not paper.abstract:
                paper.abstract = oa_paper.abstract
            if not paper.year:
                paper.year = oa_paper.year
            if not paper.authors:
                paper.authors = oa_paper.authors
            if not paper.venue:
                paper.venue = oa_paper.venue
            if not paper.citation_count:
                paper.citation_count = oa_paper.citation_count
            if not paper.openalex_id:
                paper.openalex_id = oa_paper.openalex_id
            if not paper.doi:
                paper.doi = oa_paper.doi

            # Merge raw data
            paper.raw_data.update(oa_paper.raw_data)

        return paper

    def __del__(self):
        """Close the HTTP client."""
        self.client.close()
