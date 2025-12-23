# Snowball SLR - Development Guide

## Project Overview

Snowball is a terminal-based Systematic Literature Review tool using snowballing methodology (backward/forward citation traversal). Users start with seed papers and iteratively expand their corpus through citation networks.

**Core Philosophy**: Simple, keyboard-driven workflow for scientists. Fast paper review (Tinder-style), minimal friction, version-control friendly JSON storage.

## Architecture

```
src/snowball/
├── cli.py                 # argparse CLI (init, add-seed, snowball, review, export, etc.)
├── models.py              # Pydantic models (Paper, Author, ReviewProject, FilterCriteria)
├── snowballing.py         # Core discovery engine, deduplication, iteration logic
├── paper_utils.py         # Shared formatting/filtering helpers
├── scoring.py             # Relevance scoring (TF-IDF, LLM)
├── visualization.py       # Citation network graph generation
├── storage/
│   └── json_storage.py    # Individual JSON files per paper + index
├── apis/
│   ├── base.py            # BaseAPIClient abstract class
│   ├── semantic_scholar.py, openalex.py, crossref.py, arxiv.py
│   └── aggregator.py      # Smart fallback: S2 → OpenAlex → CrossRef → arXiv
├── parsers/
│   └── pdf_parser.py      # GROBID + pypdfium2 fallback
├── exporters/
│   ├── bibtex.py, csv_exporter.py, tikz.py
└── tui/
    └── app.py             # Textual TUI (~1900 lines, main interface)
```

## Design Decisions

**JSON Storage**: Individual files per paper allow Git to track changes. Scientists can diff, merge, and version control their reviews.

**Multiple APIs**: Academic APIs have different coverage. Semantic Scholar for citations, OpenAlex for metadata, CrossRef for DOIs, arXiv for preprints. Aggregator maximizes discovery.

**Textual TUI**: Cross-platform terminal UI with keyboard-first workflow. Rich rendering without web overhead.

## Critical Gotchas

### Textual/Rich Limitations
- **No clickable links**: Rich's `[link=url]` markup crashes in Static widgets. Use `webbrowser.open()` with keyboard shortcuts instead.
- **Event.label is Rich Text**: Always convert with `str(event.label)` before string operations.
- **Widget IDs must be unique**: Don't recreate widgets with same ID in `compose()`.

### Table Refresh Pattern
```python
# CORRECT: Preserve cursor position
current_row = table.cursor_row
self._refresh_table()  # Clears and reloads
table.move_cursor(row=target_row)

# WRONG: Cursor jumps to top after refresh
self._refresh_table()
```

### None Value Handling
Papers may have None for year, citation_count, etc. Sort keys must return `(1, 0)` for None to push them to end:
```python
def _get_sort_key(paper):
    if paper.year is None:
        return (1, 0)  # Sort to end
    return (0, paper.year)  # Sort normally
```

### API Rate Limits
- Semantic Scholar: ~100 req/5min without key, 5000/5min with key
- OpenAlex & CrossRef: Use email parameter for polite pool (2x faster)

### Background Workers in TUI
Long operations (snowball, enrich, parse PDFs) use Textual workers:
```python
def action_snowball(self):
    self._worker_context["snowball"] = {"old_count": count}
    self.run_worker(do_snowball, name="snowball", thread=True)

def on_worker_state_changed(self, event):
    if event.worker.name == "snowball":
        self._handle_snowball_complete()
```

## Coding Conventions

- **Type hints everywhere** - Pydantic models for all data structures
- **GitHub dark theme colors** - See CSS in `tui/app.py` (green=included, red=excluded, yellow=pending)
- **3-state column sorting** - ascending → descending → default (Status asc)

## Testing

```bash
pytest                           # Run all tests
pytest tests/test_models.py -v   # Specific file
```

Key fixtures in `conftest.py`: `sample_paper`, `sample_papers`, `sample_project`, `storage_with_papers`

## External Docs

- Textual: https://textual.textualize.io/
- Semantic Scholar API: https://api.semanticscholar.org/api-docs/
- OpenAlex: https://docs.openalex.org/
- GROBID: https://grobid.readthedocs.io/
