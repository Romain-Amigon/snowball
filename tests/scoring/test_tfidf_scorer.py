"""Tests for TF-IDF based relevance scoring."""

import pytest
from snowball.scoring.tfidf_scorer import TFIDFScorer
from snowball.scoring import get_scorer
from snowball.models import Paper, PaperSource


@pytest.fixture
def sample_rq():
    """Sample research question for testing."""
    return "How does machine learning improve healthcare diagnosis?"


@pytest.fixture
def sample_papers():
    """Sample papers with varying relevance to the RQ."""
    return [
        Paper(
            id="p1",
            title="Deep Learning for Medical Image Analysis",
            abstract="This paper presents deep learning methods for diagnosing diseases from medical images using convolutional neural networks.",
            source=PaperSource.SEED,
        ),
        Paper(
            id="p2",
            title="Survey of Natural Language Processing",
            abstract="A comprehensive survey of NLP techniques for text classification and sentiment analysis.",
            source=PaperSource.BACKWARD,
        ),
        Paper(
            id="p3",
            title="Machine Learning in Clinical Decision Support",
            abstract="We explore ML applications for clinical diagnosis and treatment recommendations in hospitals.",
            source=PaperSource.FORWARD,
        ),
    ]


class TestTFIDFScorer:
    """Tests for TFIDFScorer class."""

    def test_score_papers_returns_scores(self, sample_rq, sample_papers):
        """Test that scoring returns valid scores for all papers."""
        scorer = TFIDFScorer()
        results = scorer.score_papers(sample_rq, sample_papers)

        assert len(results) == 3
        for paper, score in results:
            assert isinstance(paper, Paper)
            assert isinstance(score, float)
            assert 0.0 <= score <= 1.0

    def test_relevant_paper_scores_higher(self, sample_rq, sample_papers):
        """Test that more relevant papers score higher."""
        scorer = TFIDFScorer()
        results = scorer.score_papers(sample_rq, sample_papers)

        scores = {r[0].id: r[1] for r in results}

        # ML/healthcare papers should score higher than NLP survey
        assert scores["p1"] > scores["p2"], "Medical ML paper should score higher than NLP survey"
        assert scores["p3"] > scores["p2"], "Clinical ML paper should score higher than NLP survey"

    def test_empty_papers_list(self, sample_rq):
        """Test handling of empty papers list."""
        scorer = TFIDFScorer()
        results = scorer.score_papers(sample_rq, [])
        assert results == []

    def test_paper_without_abstract(self, sample_rq):
        """Test scoring paper with only title (no abstract)."""
        papers = [
            Paper(
                id="p1",
                title="Machine Learning for Healthcare",
                source=PaperSource.SEED,
            )
        ]
        scorer = TFIDFScorer()
        results = scorer.score_papers(sample_rq, papers)

        assert len(results) == 1
        paper, score = results[0]
        assert 0.0 <= score <= 1.0
        # Should still get a reasonable score from title alone
        assert score > 0.0

    def test_progress_callback_called(self, sample_rq, sample_papers):
        """Test that progress callback is invoked correctly."""
        scorer = TFIDFScorer()
        calls = []

        def callback(current, total):
            calls.append((current, total))

        scorer.score_papers(sample_rq, sample_papers, callback)

        assert len(calls) > 0
        # Last call should have current == total
        assert calls[-1][0] == len(sample_papers)
        assert calls[-1][1] == len(sample_papers)

    def test_identical_text_scores_high(self):
        """Test that identical text gets high score."""
        rq = "Machine learning for medical diagnosis"
        papers = [
            Paper(
                id="p1",
                title="Machine learning for medical diagnosis",
                abstract="Machine learning for medical diagnosis applications.",
                source=PaperSource.SEED,
            )
        ]
        scorer = TFIDFScorer()
        results = scorer.score_papers(rq, papers)

        paper, score = results[0]
        assert score > 0.5, "Identical text should have high score"

    def test_unrelated_text_scores_low(self):
        """Test that unrelated text gets low score."""
        rq = "Machine learning for medical diagnosis"
        papers = [
            Paper(
                id="p1",
                title="Ancient Roman Architecture",
                abstract="A study of architectural styles in ancient Rome and their influence.",
                source=PaperSource.SEED,
            )
        ]
        scorer = TFIDFScorer()
        results = scorer.score_papers(rq, papers)

        paper, score = results[0]
        assert score < 0.3, "Unrelated text should have low score"


class TestGetScorer:
    """Tests for the get_scorer factory function."""

    def test_get_tfidf_scorer(self):
        """Test getting TF-IDF scorer."""
        scorer = get_scorer("tfidf")
        assert isinstance(scorer, TFIDFScorer)

    def test_invalid_method_raises(self):
        """Test that invalid method raises ValueError."""
        with pytest.raises(ValueError, match="Unknown scoring method.*tfidf.*llm"):
            get_scorer("invalid_method")
