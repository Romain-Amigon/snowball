"""Tests for Pydantic data models."""

from datetime import datetime

from snowball.models import (
    Paper,
    Author,
    Venue,
    PaperStatus,
    PaperSource,
    ExclusionType,
    FilterCriteria,
    IterationStats,
    ReviewProject,
)


class TestPaperStatus:
    """Tests for PaperStatus enum."""

    def test_enum_values(self):
        """Test that PaperStatus has correct values."""
        assert PaperStatus.PENDING.value == "pending"
        assert PaperStatus.INCLUDED.value == "included"
        assert PaperStatus.EXCLUDED.value == "excluded"
        assert PaperStatus.MAYBE.value == "maybe"

    def test_enum_is_string(self):
        """Test that PaperStatus values are strings."""
        for status in PaperStatus:
            assert isinstance(status.value, str)


class TestPaperSource:
    """Tests for PaperSource enum."""

    def test_enum_values(self):
        """Test that PaperSource has correct values."""
        assert PaperSource.SEED.value == "seed"
        assert PaperSource.BACKWARD.value == "backward"
        assert PaperSource.FORWARD.value == "forward"


class TestExclusionType:
    """Tests for ExclusionType enum."""

    def test_enum_values(self):
        """Test that ExclusionType has correct values."""
        assert ExclusionType.AUTO.value == "auto"
        assert ExclusionType.MANUAL.value == "manual"

    def test_enum_is_string(self):
        """Test that ExclusionType values are strings."""
        for exclusion_type in ExclusionType:
            assert isinstance(exclusion_type.value, str)


class TestAuthor:
    """Tests for Author model."""

    def test_create_author_with_name_only(self):
        """Test creating author with only name."""
        author = Author(name="John Doe")
        assert author.name == "John Doe"
        assert author.affiliations is None

    def test_create_author_with_affiliations(self):
        """Test creating author with affiliations."""
        author = Author(name="John Doe", affiliations=["MIT", "Harvard"])
        assert author.name == "John Doe"
        assert author.affiliations == ["MIT", "Harvard"]

    def test_author_serialization(self):
        """Test that author can be serialized to dict."""
        author = Author(name="John Doe", affiliations=["MIT"])
        data = author.model_dump()
        assert data["name"] == "John Doe"
        assert data["affiliations"] == ["MIT"]


class TestVenue:
    """Tests for Venue model."""

    def test_create_venue_minimal(self):
        """Test creating venue with minimal fields."""
        venue = Venue()
        assert venue.name is None
        assert venue.type is None
        assert venue.year is None

    def test_create_venue_full(self):
        """Test creating venue with all fields."""
        venue = Venue(
            name="Nature",
            type="journal",
            year=2023,
            volume="123",
            issue="4",
            pages="100-110"
        )
        assert venue.name == "Nature"
        assert venue.type == "journal"
        assert venue.year == 2023
        assert venue.volume == "123"
        assert venue.issue == "4"
        assert venue.pages == "100-110"


class TestPaper:
    """Tests for Paper model."""

    def test_create_paper_minimal(self):
        """Test creating paper with only required fields."""
        paper = Paper(
            id="test-id",
            title="Test Title",
            source=PaperSource.SEED
        )
        assert paper.id == "test-id"
        assert paper.title == "Test Title"
        assert paper.source == PaperSource.SEED
        assert paper.status == PaperStatus.PENDING  # Default

    def test_create_paper_full(self, sample_paper):
        """Test creating paper with all fields."""
        assert sample_paper.id == "test-paper-id-123"
        assert sample_paper.doi == "10.1234/test.doi"
        assert sample_paper.arxiv_id == "2301.00001"
        assert sample_paper.title == "A Test Paper Title"
        assert len(sample_paper.authors) == 1
        assert sample_paper.year == 2023
        assert sample_paper.citation_count == 100
        assert sample_paper.status == PaperStatus.PENDING
        assert sample_paper.source == PaperSource.SEED

    def test_paper_default_values(self):
        """Test that paper has correct default values."""
        paper = Paper(
            id="test-id",
            title="Test Title",
            source=PaperSource.SEED
        )
        assert paper.authors == []
        assert paper.references == []
        assert paper.citations == []
        assert paper.tags == []
        assert paper.notes == ""
        assert paper.snowball_iteration == 0
        assert paper.raw_data == {}

    def test_paper_serialization(self, sample_paper):
        """Test that paper can be serialized to dict."""
        data = sample_paper.model_dump(mode='json')
        assert isinstance(data, dict)
        assert data["id"] == "test-paper-id-123"
        assert data["title"] == "A Test Paper Title"
        # Check enum values are serialized as strings
        assert data["status"] == "pending"
        assert data["source"] == "seed"

    def test_paper_deserialization(self, sample_paper):
        """Test that paper can be deserialized from dict."""
        data = sample_paper.model_dump(mode='json')
        restored_paper = Paper.model_validate(data)
        assert restored_paper.id == sample_paper.id
        assert restored_paper.title == sample_paper.title
        assert restored_paper.status == sample_paper.status

    def test_paper_with_none_values(self):
        """Test paper with optional fields as None."""
        paper = Paper(
            id="test-id",
            title="Test Title",
            source=PaperSource.SEED,
            year=None,
            citation_count=None,
            abstract=None,
            doi=None
        )
        assert paper.year is None
        assert paper.citation_count is None

    def test_paper_exclusion_type_default(self):
        """Test that paper exclusion_type defaults to None."""
        paper = Paper(
            id="test-id",
            title="Test Title",
            source=PaperSource.SEED
        )
        assert paper.exclusion_type is None

    def test_paper_exclusion_type_auto(self):
        """Test paper with auto exclusion type."""
        paper = Paper(
            id="test-id",
            title="Test Title",
            source=PaperSource.BACKWARD,
            status=PaperStatus.EXCLUDED,
            exclusion_type=ExclusionType.AUTO
        )
        assert paper.exclusion_type == ExclusionType.AUTO

    def test_paper_exclusion_type_manual(self):
        """Test paper with manual exclusion type."""
        paper = Paper(
            id="test-id",
            title="Test Title",
            source=PaperSource.BACKWARD,
            status=PaperStatus.EXCLUDED,
            exclusion_type=ExclusionType.MANUAL
        )
        assert paper.exclusion_type == ExclusionType.MANUAL

    def test_paper_exclusion_type_serialization(self):
        """Test that exclusion_type is properly serialized."""
        paper = Paper(
            id="test-id",
            title="Test Title",
            source=PaperSource.SEED,
            exclusion_type=ExclusionType.AUTO
        )
        data = paper.model_dump(mode='json')
        assert data["exclusion_type"] == "auto"

        # Test deserialization
        restored = Paper.model_validate(data)
        assert restored.exclusion_type == ExclusionType.AUTO


class TestFilterCriteria:
    """Tests for FilterCriteria model."""

    def test_create_empty_criteria(self):
        """Test creating empty filter criteria."""
        criteria = FilterCriteria()
        assert criteria.min_year is None
        assert criteria.max_year is None
        assert criteria.keywords == []
        assert criteria.excluded_keywords == []

    def test_create_criteria_with_years(self):
        """Test creating criteria with year range."""
        criteria = FilterCriteria(min_year=2020, max_year=2024)
        assert criteria.min_year == 2020
        assert criteria.max_year == 2024

    def test_create_criteria_with_keywords(self):
        """Test creating criteria with keywords."""
        criteria = FilterCriteria(
            keywords=["machine learning", "AI"],
            excluded_keywords=["survey"]
        )
        assert "machine learning" in criteria.keywords
        assert "survey" in criteria.excluded_keywords

    def test_create_criteria_full(self, sample_filter_criteria):
        """Test creating criteria with all fields."""
        assert sample_filter_criteria.min_year == 2020
        assert sample_filter_criteria.max_year == 2024
        assert sample_filter_criteria.min_citations == 10
        assert sample_filter_criteria.max_citations == 1000
        assert len(sample_filter_criteria.keywords) == 2
        assert sample_filter_criteria.min_influential_citations == 5


class TestIterationStats:
    """Tests for IterationStats model."""

    def test_create_iteration_stats_minimal(self):
        """Test creating iteration stats with only iteration number."""
        stats = IterationStats(iteration=1)
        assert stats.iteration == 1
        assert stats.discovered == 0
        assert stats.backward == 0
        assert stats.forward == 0
        assert stats.auto_excluded == 0
        assert stats.for_review == 0
        assert stats.manual_included == 0
        assert stats.manual_excluded == 0
        assert stats.manual_maybe == 0
        assert stats.reviewed == 0

    def test_create_iteration_stats_full(self):
        """Test creating iteration stats with all fields."""
        stats = IterationStats(
            iteration=2,
            discovered=50,
            backward=30,
            forward=20,
            auto_excluded=10,
            for_review=40,
            manual_included=15,
            manual_excluded=20,
            manual_maybe=5,
            reviewed=40
        )
        assert stats.iteration == 2
        assert stats.discovered == 50
        assert stats.backward == 30
        assert stats.forward == 20
        assert stats.auto_excluded == 10
        assert stats.for_review == 40
        assert stats.manual_included == 15
        assert stats.manual_excluded == 20
        assert stats.manual_maybe == 5
        assert stats.reviewed == 40

    def test_iteration_stats_has_timestamp(self):
        """Test that iteration stats has timestamp."""
        stats = IterationStats(iteration=1)
        assert stats.timestamp is not None
        assert isinstance(stats.timestamp, datetime)

    def test_iteration_stats_serialization(self):
        """Test that iteration stats can be serialized."""
        stats = IterationStats(
            iteration=1,
            discovered=10,
            auto_excluded=2,
            for_review=8
        )
        data = stats.model_dump(mode='json')
        assert isinstance(data, dict)
        assert data["iteration"] == 1
        assert data["discovered"] == 10
        assert data["auto_excluded"] == 2
        assert data["for_review"] == 8

    def test_iteration_stats_deserialization(self):
        """Test that iteration stats can be deserialized."""
        stats = IterationStats(
            iteration=1,
            discovered=10,
            backward=6,
            forward=4
        )
        data = stats.model_dump(mode='json')
        restored = IterationStats.model_validate(data)
        assert restored.iteration == stats.iteration
        assert restored.discovered == stats.discovered
        assert restored.backward == stats.backward
        assert restored.forward == stats.forward


class TestReviewProject:
    """Tests for ReviewProject model."""

    def test_create_project_minimal(self):
        """Test creating project with only name."""
        project = ReviewProject(name="Test Project")
        assert project.name == "Test Project"
        assert project.description == ""
        assert project.current_iteration == 0

    def test_create_project_full(self, sample_project):
        """Test creating project with all fields."""
        assert sample_project.name == "Test Project"
        assert sample_project.description == "A test systematic literature review project"
        assert sample_project.current_iteration == 1
        assert len(sample_project.seed_paper_ids) == 1

    def test_project_created_at_default(self):
        """Test that project has created_at timestamp."""
        project = ReviewProject(name="Test")
        assert project.created_at is not None
        assert isinstance(project.created_at, datetime)

    def test_project_serialization(self, sample_project):
        """Test that project can be serialized to dict."""
        data = sample_project.model_dump(mode='json')
        assert isinstance(data, dict)
        assert data["name"] == "Test Project"
        assert data["current_iteration"] == 1

    def test_project_deserialization(self, sample_project):
        """Test that project can be deserialized from dict."""
        data = sample_project.model_dump(mode='json')
        restored = ReviewProject.model_validate(data)
        assert restored.name == sample_project.name
        assert restored.current_iteration == sample_project.current_iteration

    def test_project_iteration_stats_default(self):
        """Test that project iteration_stats defaults to empty dict."""
        project = ReviewProject(name="Test Project")
        assert project.iteration_stats == {}

    def test_project_with_iteration_stats(self):
        """Test project with iteration stats."""
        stats = IterationStats(
            iteration=1,
            discovered=20,
            backward=12,
            forward=8,
            auto_excluded=5,
            for_review=15
        )
        project = ReviewProject(
            name="Test Project",
            iteration_stats={1: stats}
        )
        assert 1 in project.iteration_stats
        assert project.iteration_stats[1].discovered == 20
        assert project.iteration_stats[1].backward == 12

    def test_project_iteration_stats_serialization(self):
        """Test that project with iteration stats can be serialized."""
        stats = IterationStats(
            iteration=1,
            discovered=10,
            auto_excluded=2
        )
        project = ReviewProject(
            name="Test Project",
            iteration_stats={1: stats}
        )
        data = project.model_dump(mode='json')
        assert "iteration_stats" in data
        assert "1" in data["iteration_stats"] or 1 in data["iteration_stats"]

        # Test deserialization
        restored = ReviewProject.model_validate(data)
        assert 1 in restored.iteration_stats
        assert restored.iteration_stats[1].discovered == 10
