"""BibTeX export functionality."""

import re
from typing import List
from ..models import Paper, PaperStatus


class BibTeXExporter:
    """Exports papers to BibTeX format."""

    def export(self, papers: List[Paper], only_included: bool = True) -> str:
        """Export papers to BibTeX format.

        Args:
            papers: List of papers to export
            only_included: Only export included papers

        Returns:
            BibTeX formatted string
        """
        if only_included:
            papers = [p for p in papers if p.status == PaperStatus.INCLUDED]

        entries = []
        for paper in papers:
            entry = self._create_bibtex_entry(paper)
            if entry:
                entries.append(entry)

        return "\n\n".join(entries)

    def _create_bibtex_entry(self, paper: Paper) -> str:
        """Create a BibTeX entry for a paper."""
        # Generate citation key
        cite_key = self._generate_cite_key(paper)

        # Determine entry type
        entry_type = self._determine_entry_type(paper)

        # Build fields
        fields = []

        # Title
        if paper.title:
            fields.append(f'  title = {{{paper.title}}}')

        # Authors
        if paper.authors:
            authors_str = " and ".join([author.name for author in paper.authors])
            fields.append(f'  author = {{{authors_str}}}')

        # Year
        if paper.year:
            fields.append(f'  year = {{{paper.year}}}')

        # Venue information
        if paper.venue:
            if entry_type == "article" and paper.venue.name:
                fields.append(f'  journal = {{{paper.venue.name}}}')
            elif entry_type in ["inproceedings", "conference"] and paper.venue.name:
                fields.append(f'  booktitle = {{{paper.venue.name}}}')

            if paper.venue.volume:
                fields.append(f'  volume = {{{paper.venue.volume}}}')
            if paper.venue.issue:
                fields.append(f'  number = {{{paper.venue.issue}}}')
            if paper.venue.pages:
                fields.append(f'  pages = {{{paper.venue.pages}}}')

        # DOI
        if paper.doi:
            fields.append(f'  doi = {{{paper.doi}}}')

        # Abstract
        if paper.abstract:
            # Clean abstract for BibTeX
            clean_abstract = paper.abstract.replace('{', '').replace('}', '')
            clean_abstract = clean_abstract.replace('\n', ' ')
            fields.append(f'  abstract = {{{clean_abstract}}}')

        # Additional identifiers
        if paper.arxiv_id:
            fields.append(f'  eprint = {{{paper.arxiv_id}}}')
            fields.append(f'  archivePrefix = {{arXiv}}')

        if paper.pmid:
            fields.append(f'  pmid = {{{paper.pmid}}}')

        # Construct entry
        fields_str = ',\n'.join(fields)
        entry = f'@{entry_type}{{{cite_key},\n{fields_str}\n}}'

        return entry

    def _generate_cite_key(self, paper: Paper) -> str:
        """Generate a citation key for the paper."""
        # Format: FirstAuthorLastNameYearFirstWord
        parts = []

        # First author's last name
        if paper.authors:
            first_author = paper.authors[0].name
            # Try to extract last name
            name_parts = first_author.split()
            if name_parts:
                last_name = name_parts[-1]
                # Remove non-alphanumeric characters
                last_name = re.sub(r'[^a-zA-Z]', '', last_name)
                parts.append(last_name)

        # Year
        if paper.year:
            parts.append(str(paper.year))

        # First meaningful word from title
        if paper.title:
            title_words = paper.title.split()
            # Skip common articles
            skip_words = {'the', 'a', 'an', 'on', 'in', 'of', 'for', 'and', 'or', 'to'}
            for word in title_words:
                clean_word = re.sub(r'[^a-zA-Z]', '', word).lower()
                if clean_word and clean_word not in skip_words:
                    parts.append(clean_word.capitalize())
                    break

        if not parts:
            # Fallback to paper ID
            return f"paper{paper.id[:8]}"

        return "".join(parts)

    def _determine_entry_type(self, paper: Paper) -> str:
        """Determine the BibTeX entry type for a paper."""
        if not paper.venue or not paper.venue.type:
            return "article"  # Default

        venue_type = paper.venue.type.lower()

        # Map venue types to BibTeX types
        if "journal" in venue_type:
            return "article"
        elif "conference" in venue_type or "proceedings" in venue_type:
            return "inproceedings"
        elif "workshop" in venue_type:
            return "inproceedings"
        elif "book" in venue_type:
            return "book"
        elif "thesis" in venue_type or "dissertation" in venue_type:
            return "phdthesis"
        elif "preprint" in venue_type or "arxiv" in venue_type:
            return "misc"
        else:
            return "article"
