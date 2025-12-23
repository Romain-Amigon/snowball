"""TF-IDF based relevance scoring."""

import logging
import re
from typing import List, Optional, Callable, Tuple, TYPE_CHECKING

from .base import BaseScorer

if TYPE_CHECKING:
    from ..models import Paper

logger = logging.getLogger(__name__)

# Common English stopwords for fallback scoring
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "he", "in", "is", "it", "its", "of", "on", "that", "the",
    "to", "was", "were", "will", "with", "the", "this", "but", "they",
    "have", "had", "what", "when", "where", "who", "which", "why", "how",
    "all", "each", "every", "both", "few", "more", "most", "other",
    "some", "such", "no", "nor", "not", "only", "own", "same", "so",
    "than", "too", "very", "can", "just", "should", "now", "or", "if",
    "our", "we", "their", "been", "being", "do", "does", "did", "doing",
    "would", "could", "might", "must", "shall", "may", "about", "into",
    "through", "during", "before", "after", "above", "below", "between",
    "under", "again", "further", "then", "once", "here", "there", "any",
}


class TFIDFScorer(BaseScorer):
    """Score papers using TF-IDF + Cosine similarity."""

    def __init__(self):
        """Initialize scorer, checking for sklearn availability."""
        self._use_sklearn = False
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity

            self._vectorizer_class = TfidfVectorizer
            self._cosine_similarity = cosine_similarity
            self._use_sklearn = True
            logger.debug("Using scikit-learn for TF-IDF scoring")
        except ImportError:
            logger.info("scikit-learn not available, using word overlap fallback")

    def score_papers(
        self,
        research_question: str,
        papers: List["Paper"],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Tuple["Paper", float]]:
        """Score papers using TF-IDF similarity."""
        if not papers:
            return []

        if self._use_sklearn:
            return self._score_with_sklearn(research_question, papers, progress_callback)
        else:
            return self._score_with_word_overlap(research_question, papers, progress_callback)

    def _score_with_sklearn(
        self,
        research_question: str,
        papers: List["Paper"],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Tuple["Paper", float]]:
        """Score using sklearn TF-IDF vectorizer."""
        # Prepare documents: RQ first, then all papers
        documents = [research_question]

        for paper in papers:
            text = self.get_paper_text(paper)
            documents.append(text)

        # Vectorize all documents
        vectorizer = self._vectorizer_class(
            stop_words="english",
            max_features=5000,
            ngram_range=(1, 2),  # Unigrams and bigrams
        )

        try:
            tfidf_matrix = vectorizer.fit_transform(documents)
        except ValueError:
            # Empty vocabulary (all stop words or empty documents)
            logger.warning("Empty vocabulary, returning zero scores")
            return [(paper, 0.0) for paper in papers]

        # Calculate similarity between RQ (index 0) and each paper
        rq_vector = tfidf_matrix[0:1]
        paper_vectors = tfidf_matrix[1:]

        similarities = self._cosine_similarity(rq_vector, paper_vectors).flatten()

        results = []
        total = len(papers)
        for i, (paper, score) in enumerate(zip(papers, similarities)):
            results.append((paper, float(score)))
            if progress_callback:
                progress_callback(i + 1, total)

        return results

    def _score_with_word_overlap(
        self,
        research_question: str,
        papers: List["Paper"],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Tuple["Paper", float]]:
        """Simple word overlap scoring (Jaccard similarity) as fallback."""
        rq_words = self._tokenize(research_question)

        results = []
        total = len(papers)

        for i, paper in enumerate(papers):
            text = self.get_paper_text(paper)
            paper_words = self._tokenize(text)

            if not rq_words or not paper_words:
                score = 0.0
            else:
                intersection = len(rq_words & paper_words)
                union = len(rq_words | paper_words)
                score = intersection / union if union > 0 else 0.0

            results.append((paper, score))

            if progress_callback:
                progress_callback(i + 1, total)

        return results

    def _tokenize(self, text: str) -> set:
        """Tokenize text into lowercase words, removing stopwords.

        Args:
            text: Text to tokenize

        Returns:
            Set of unique lowercase words
        """
        # Extract words (alphanumeric sequences)
        words = re.findall(r"\b[a-zA-Z]{2,}\b", text.lower())
        # Remove stopwords
        return set(words) - STOPWORDS
