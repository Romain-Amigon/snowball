"""Snowball - Systematic Literature Review using Snowballing."""

__version__ = "0.1.0"

from .models import (
    Paper,
    PaperStatus,
    PaperSource,
    Author,
    Venue,
    FilterCriteria,
    ReviewProject,
)
from .storage.json_storage import JSONStorage
from .snowballing import SnowballEngine
from .apis.aggregator import APIAggregator

__all__ = [
    "Paper",
    "PaperStatus",
    "PaperSource",
    "Author",
    "Venue",
    "FilterCriteria",
    "ReviewProject",
    "JSONStorage",
    "SnowballEngine",
    "APIAggregator",
]
