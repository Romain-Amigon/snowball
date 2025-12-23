"""Tests for LLM-based relevance scoring."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock

from snowball.models import Paper, PaperSource


class TestLLMScorer:
    """Tests for LLMScorer class."""

    @pytest.fixture
    def sample_rq(self):
        """Sample research question for testing."""
        return "How does machine learning improve healthcare diagnosis?"

    @pytest.fixture
    def sample_papers(self):
        """Sample papers for testing."""
        return [
            Paper(
                id="p1",
                title="Deep Learning for Medical Image Analysis",
                abstract="Deep learning methods for disease diagnosis.",
                source=PaperSource.SEED,
            ),
            Paper(
                id="p2",
                title="Natural Language Processing Survey",
                abstract="A survey of NLP techniques.",
                source=PaperSource.BACKWARD,
            ),
        ]

    def test_requires_api_key(self):
        """Test that LLMScorer requires an API key."""
        from snowball.scoring.llm_scorer import LLMScorer

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="API key required"):
                LLMScorer(api_key=None)

    def test_accepts_api_key_param(self):
        """Test that LLMScorer accepts API key as parameter."""
        from snowball.scoring.llm_scorer import LLMScorer

        scorer = LLMScorer(api_key="test-key")
        assert scorer.api_key == "test-key"

    def test_accepts_api_key_from_env(self):
        """Test that LLMScorer reads API key from environment."""
        from snowball.scoring.llm_scorer import LLMScorer

        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}):
            scorer = LLMScorer()
            assert scorer.api_key == "env-key"

    def test_empty_papers_list(self, sample_rq):
        """Test handling of empty papers list."""
        from snowball.scoring.llm_scorer import LLMScorer

        scorer = LLMScorer(api_key="test-key")
        results = scorer.score_papers(sample_rq, [])
        assert results == []

    def test_score_papers_returns_scores(self, sample_rq, sample_papers):
        """Test that scoring returns valid scores for all papers."""
        from snowball.scoring.llm_scorer import LLMScorer

        # Create a mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "[0.8, 0.3]"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client):
            scorer = LLMScorer(api_key="test-key")
            results = scorer.score_papers(sample_rq, sample_papers)

        assert len(results) == 2
        assert results[0][1] == 0.8
        assert results[1][1] == 0.3

    def test_handles_code_blocks_in_response(self, sample_rq, sample_papers):
        """Test that scoring handles markdown code blocks in response."""
        from snowball.scoring.llm_scorer import LLMScorer

        # Create a mock response with code blocks
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "```json\n[0.7, 0.5]\n```"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client):
            scorer = LLMScorer(api_key="test-key")
            results = scorer.score_papers(sample_rq, sample_papers)

        assert len(results) == 2
        assert results[0][1] == 0.7
        assert results[1][1] == 0.5

    def test_clamps_scores_to_valid_range(self, sample_rq, sample_papers):
        """Test that scores outside 0-1 range are clamped."""
        from snowball.scoring.llm_scorer import LLMScorer

        # Create a mock response with out-of-range scores
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "[1.5, -0.3]"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client):
            scorer = LLMScorer(api_key="test-key")
            results = scorer.score_papers(sample_rq, sample_papers)

        assert results[0][1] == 1.0  # Clamped from 1.5
        assert results[1][1] == 0.0  # Clamped from -0.3

    def test_handles_api_error_gracefully(self, sample_rq, sample_papers):
        """Test that API errors are handled gracefully."""
        from snowball.scoring.llm_scorer import LLMScorer

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        with patch("openai.OpenAI", return_value=mock_client):
            scorer = LLMScorer(api_key="test-key")
            results = scorer.score_papers(sample_rq, sample_papers)

        # Should return 0.0 for all papers on error
        assert len(results) == 2
        assert results[0][1] == 0.0
        assert results[1][1] == 0.0

    def test_handles_invalid_json_response(self, sample_rq, sample_papers):
        """Test that invalid JSON responses are handled gracefully."""
        from snowball.scoring.llm_scorer import LLMScorer

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not valid json"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client):
            scorer = LLMScorer(api_key="test-key")
            results = scorer.score_papers(sample_rq, sample_papers)

        # Should return 0.0 for all papers on parse error
        assert len(results) == 2
        assert results[0][1] == 0.0
        assert results[1][1] == 0.0

    def test_progress_callback_called(self, sample_rq, sample_papers):
        """Test that progress callback is invoked correctly."""
        from snowball.scoring.llm_scorer import LLMScorer

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "[0.5, 0.5]"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client):
            scorer = LLMScorer(api_key="test-key")

            calls = []

            def callback(current, total):
                calls.append((current, total))

            scorer.score_papers(sample_rq, sample_papers, callback)

        assert len(calls) > 0
        # Last call should have current == total
        assert calls[-1][0] == len(sample_papers)


class TestGetScorerLLM:
    """Tests for get_scorer with LLM method."""

    def test_get_llm_scorer(self):
        """Test getting LLM scorer."""
        from snowball.scoring import get_scorer

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            scorer = get_scorer("llm")
            assert scorer.__class__.__name__ == "LLMScorer"

    def test_get_llm_scorer_with_custom_model(self):
        """Test getting LLM scorer with custom model."""
        from snowball.scoring import get_scorer

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            scorer = get_scorer("llm", model="gpt-4")
            assert scorer.model == "gpt-4"
