"""arXiv API client."""

import logging
import time
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Any
import httpx

from .base import BaseAPIClient, APINotFoundError
from ..models import Paper, Author, Venue, PaperSource
from ..storage.json_storage import JSONStorage

logger = logging.getLogger(__name__)


class ArXivClient(BaseAPIClient):
    """Client for arXiv API."""

    BASE_URL = "http://export.arxiv.org/api/query"

    def __init__(self, rate_limit_delay: float = 3.0):
        """Initialize arXiv client.

        Args:
            rate_limit_delay: Delay between requests (arXiv recommends 3 seconds)
        """
        self.rate_limit_delay = rate_limit_delay
        self.client = httpx.Client(timeout=30.0)

    def _make_request(self, params: Dict[str, str]) -> str:
        """Make a request to the arXiv API.

        Returns:
            XML response as string
        """
        try:
            time.sleep(self.rate_limit_delay)
            response = self.client.get(self.BASE_URL, params=params)

            if response.status_code != 200:
                logger.error(f"API error: {response.status_code}")
                return ""

            return response.text

        except httpx.TimeoutException:
            logger.warning(f"Timeout requesting arXiv API")
            return ""

    def _parse_entry(self, entry: ET.Element, source: PaperSource = PaperSource.SEED) -> Optional[Paper]:
        """Parse an arXiv entry from XML."""
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'arxiv': 'http://arxiv.org/schemas/atom'
        }

        try:
            # Extract arXiv ID
            arxiv_id_elem = entry.find('atom:id', ns)
            arxiv_id = None
            if arxiv_id_elem is not None and arxiv_id_elem.text:
                # Extract ID from URL (e.g., http://arxiv.org/abs/1234.5678v1 -> 1234.5678)
                arxiv_id = arxiv_id_elem.text.split('/abs/')[-1].split('v')[0]

            # Extract title
            title_elem = entry.find('atom:title', ns)
            title = title_elem.text.strip() if title_elem is not None else "Unknown Title"

            # Extract authors
            authors = []
            for author_elem in entry.findall('atom:author', ns):
                name_elem = author_elem.find('atom:name', ns)
                if name_elem is not None and name_elem.text:
                    authors.append(Author(name=name_elem.text.strip()))

            # Extract abstract
            summary_elem = entry.find('atom:summary', ns)
            abstract = summary_elem.text.strip() if summary_elem is not None else None

            # Extract publication year from published date
            published_elem = entry.find('atom:published', ns)
            year = None
            if published_elem is not None and published_elem.text:
                year_str = published_elem.text[:4]
                try:
                    year = int(year_str)
                except ValueError:
                    pass

            # Extract DOI if available
            doi = None
            doi_elem = entry.find('arxiv:doi', ns)
            if doi_elem is not None and doi_elem.text:
                doi = doi_elem.text.strip()

            # Extract categories for venue
            primary_category = entry.find('arxiv:primary_category', ns)
            category = None
            if primary_category is not None:
                category = primary_category.get('term')

            venue = Venue(
                name=f"arXiv ({category})" if category else "arXiv",
                year=year,
                type="preprint"
            )

            # Create paper
            paper = Paper(
                id=JSONStorage.generate_id(),
                arxiv_id=arxiv_id,
                doi=doi,
                title=title,
                authors=authors,
                year=year,
                abstract=abstract,
                venue=venue,
                source=source,
                raw_data={"arxiv_category": category}
            )

            return paper

        except Exception as e:
            logger.error(f"Error parsing arXiv entry: {e}")
            return None

    def search_by_arxiv_id(self, arxiv_id: str) -> Optional[Paper]:
        """Search for a paper by arXiv ID."""
        try:
            response_xml = self._make_request({"id_list": arxiv_id})

            if not response_xml:
                return None

            root = ET.fromstring(response_xml)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}

            entry = root.find('atom:entry', ns)
            if entry is not None:
                return self._parse_entry(entry)

        except Exception as e:
            logger.error(f"Error searching by arXiv ID {arxiv_id}: {e}")

        return None

    def search_by_doi(self, doi: str) -> Optional[Paper]:
        """Search for a paper by DOI.

        Note: arXiv search by DOI is limited.
        """
        # arXiv doesn't have great DOI search, so we return None
        return None

    def search_by_title(self, title: str) -> Optional[Paper]:
        """Search for a paper by title."""
        try:
            # Clean title for search
            search_query = f'ti:"{title}"'

            response_xml = self._make_request({
                "search_query": search_query,
                "max_results": "1"
            })

            if not response_xml:
                return None

            root = ET.fromstring(response_xml)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}

            entry = root.find('atom:entry', ns)
            if entry is not None:
                return self._parse_entry(entry)

        except Exception as e:
            logger.error(f"Error searching by title '{title}': {e}")

        return None

    def get_references(self, paper_id: str) -> List[Paper]:
        """Get papers referenced by this paper.

        Note: arXiv API doesn't provide reference data.
        """
        logger.info("arXiv API doesn't provide reference data")
        return []

    def get_citations(self, paper_id: str) -> List[Paper]:
        """Get papers citing this paper.

        Note: arXiv API doesn't provide citation data.
        """
        logger.info("arXiv API doesn't provide citation data")
        return []

    def enrich_metadata(self, paper: Paper) -> Paper:
        """Enrich paper metadata using arXiv."""
        arxiv_paper = None

        if paper.arxiv_id:
            arxiv_paper = self.search_by_arxiv_id(paper.arxiv_id)
        elif paper.title:
            arxiv_paper = self.search_by_title(paper.title)

        if arxiv_paper:
            # Merge data
            if not paper.title or paper.title == "Unknown Title":
                paper.title = arxiv_paper.title
            if not paper.abstract:
                paper.abstract = arxiv_paper.abstract
            if not paper.year:
                paper.year = arxiv_paper.year
            if not paper.authors:
                paper.authors = arxiv_paper.authors
            if not paper.arxiv_id:
                paper.arxiv_id = arxiv_paper.arxiv_id
            if not paper.doi:
                paper.doi = arxiv_paper.doi

            # Update venue if it's a preprint
            if not paper.venue or paper.venue.type == "preprint":
                paper.venue = arxiv_paper.venue

            # Merge raw data
            paper.raw_data.update(arxiv_paper.raw_data)

        return paper

    def __del__(self):
        """Close the HTTP client."""
        self.client.close()
