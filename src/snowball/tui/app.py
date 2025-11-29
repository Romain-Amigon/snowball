"""Main TUI application using Textual."""

from pathlib import Path
from typing import Optional, List
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header,
    Footer,
    DataTable,
    Static,
    Button,
    Input,
    Label,
    TextArea,
    Select,
)
from textual.binding import Binding
from textual.screen import Screen, ModalScreen
from textual import events
from rich.text import Text

from ..models import Paper, PaperStatus, ReviewProject, FilterCriteria
from ..storage.json_storage import JSONStorage
from ..snowballing import SnowballEngine
from ..apis.aggregator import APIAggregator
from ..parsers.pdf_parser import PDFParser
from ..exporters.bibtex import BibTeXExporter
from ..exporters.csv_exporter import CSVExporter


class PaperDetailView(Static):
    """Widget to display detailed information about a paper."""

    def __init__(self, paper: Optional[Paper] = None):
        super().__init__()
        self.paper = paper

    def compose(self) -> ComposeResult:
        if not self.paper:
            yield Label("No paper selected")
            return

        # Format paper details
        details = self._format_paper_details()
        yield Static(details, id="paper-details")

    def _format_paper_details(self) -> str:
        """Format paper details as rich text."""
        if not self.paper:
            return ""

        lines = []
        lines.append(f"[bold]{self.paper.title}[/bold]\n")

        # Authors
        if self.paper.authors:
            authors_str = ", ".join([a.name for a in self.paper.authors[:5]])
            if len(self.paper.authors) > 5:
                authors_str += f" (+{len(self.paper.authors) - 5} more)"
            lines.append(f"[cyan]Authors:[/cyan] {authors_str}")

        # Year and venue
        year_venue = []
        if self.paper.year:
            year_venue.append(str(self.paper.year))
        if self.paper.venue and self.paper.venue.name:
            year_venue.append(self.paper.venue.name)
        if year_venue:
            lines.append(f"[cyan]Published:[/cyan] {' - '.join(year_venue)}")

        # Identifiers
        ids = []
        if self.paper.doi:
            ids.append(f"DOI: {self.paper.doi}")
        if self.paper.arxiv_id:
            ids.append(f"arXiv: {self.paper.arxiv_id}")
        if ids:
            lines.append(f"[cyan]IDs:[/cyan] {', '.join(ids)}")

        # Metrics
        if self.paper.citation_count is not None:
            cit_text = f"Citations: {self.paper.citation_count}"
            if self.paper.influential_citation_count:
                cit_text += f" (influential: {self.paper.influential_citation_count})"
            lines.append(f"[cyan]Impact:[/cyan] {cit_text}")

        # Review info
        status_color = {
            "included": "green",
            "excluded": "red",
            "pending": "yellow",
            "maybe": "blue"
        }.get(self.paper.status.value if hasattr(self.paper.status, 'value') else self.paper.status, "white")

        lines.append(f"[cyan]Status:[/cyan] [{status_color}]{self.paper.status.value if hasattr(self.paper.status, 'value') else self.paper.status}[/{status_color}]")
        lines.append(f"[cyan]Source:[/cyan] {self.paper.source.value if hasattr(self.paper.source, 'value') else self.paper.source} (iteration {self.paper.snowball_iteration})")

        # Abstract
        if self.paper.abstract:
            lines.append(f"\n[cyan]Abstract:[/cyan]")
            abstract_preview = self.paper.abstract[:500]
            if len(self.paper.abstract) > 500:
                abstract_preview += "..."
            lines.append(abstract_preview)

        # Notes
        if self.paper.notes:
            lines.append(f"\n[cyan]Notes:[/cyan]")
            lines.append(self.paper.notes)

        return "\n".join(lines)

    def update_paper(self, paper: Optional[Paper]) -> None:
        """Update the displayed paper."""
        self.paper = paper
        if self.is_mounted:
            self.remove_children()
            for widget in self.compose():
                self.mount(widget)


class ReviewDialog(ModalScreen[Optional[tuple]]):
    """Modal dialog for reviewing a paper."""

    def __init__(self, paper: Paper):
        super().__init__()
        self.paper = paper

    def compose(self) -> ComposeResult:
        with Container(id="review-dialog"):
            yield Label(f"Review: {self.paper.title[:60]}...")
            yield Label("\nStatus:")
            yield Select(
                [
                    ("Include", "included"),
                    ("Exclude", "excluded"),
                    ("Maybe", "maybe"),
                    ("Keep Pending", "pending"),
                ],
                value=self.paper.status.value if hasattr(self.paper.status, 'value') else self.paper.status,
                id="status-select"
            )
            yield Label("\nNotes:")
            yield TextArea(self.paper.notes or "", id="notes-input")
            with Horizontal():
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            status_widget = self.query_one("#status-select", Select)
            notes_widget = self.query_one("#notes-input", TextArea)

            status = status_widget.value
            notes = notes_widget.text

            self.dismiss((status, notes))
        else:
            self.dismiss(None)


class SnowballApp(App):
    """Main Snowball SLR application."""

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 2fr 1fr;
    }

    #papers-table {
        height: 100%;
        width: 100%;
    }

    #detail-panel {
        height: 100%;
        border-left: solid $primary;
        padding: 1;
    }

    #paper-details {
        height: auto;
    }

    #stats-panel {
        height: 10;
        padding: 1;
        border: solid $primary;
    }

    #review-dialog {
        width: 60;
        height: 25;
        border: thick $background 80%;
        background: $surface;
        padding: 1;
    }

    Button {
        margin: 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "review", "Review"),
        Binding("s", "snowball", "Run Snowball"),
        Binding("e", "export", "Export"),
        Binding("f", "filter", "Filter"),
    ]

    def __init__(
        self,
        project_dir: Path,
        storage: JSONStorage,
        engine: SnowballEngine,
        project: ReviewProject
    ):
        super().__init__()
        self.project_dir = project_dir
        self.storage = storage
        self.engine = engine
        self.project = project
        self.current_paper: Optional[Paper] = None

    def compose(self) -> ComposeResult:
        yield Header()

        # Left panel: Papers table
        with Vertical(id="left-panel"):
            yield Static(self._get_stats_text(), id="stats-panel")
            yield DataTable(id="papers-table", cursor_type="row")

        # Right panel: Paper details
        with ScrollableContainer(id="detail-panel"):
            yield PaperDetailView()

        yield Footer()

    def on_mount(self) -> None:
        """Set up the table when app starts."""
        table = self.query_one("#papers-table", DataTable)

        # Add columns
        table.add_columns("Status", "Title", "Year", "Citations", "Source", "Iter")

        # Load and display papers
        self._refresh_table()

    def _refresh_table(self) -> None:
        """Refresh the papers table."""
        table = self.query_one("#papers-table", DataTable)
        table.clear()

        papers = self.storage.load_all_papers()

        # Sort papers by iteration, then status
        papers.sort(key=lambda p: (p.snowball_iteration, p.status.value if hasattr(p.status, 'value') else p.status))

        for paper in papers:
            # Status indicator
            status_val = paper.status.value if hasattr(paper.status, 'value') else paper.status
            status_icon = {
                "included": "[green]✓[/green]",
                "excluded": "[red]✗[/red]",
                "pending": "[yellow]?[/yellow]",
                "maybe": "[blue]~[/blue]"
            }.get(status_val, "?")

            # Title (truncated)
            title = paper.title[:50] + "..." if len(paper.title) > 50 else paper.title

            # Citations
            citations = str(paper.citation_count) if paper.citation_count is not None else "-"

            # Source
            source = paper.source.value if hasattr(paper.source, 'value') else paper.source
            source_short = source[0].upper()

            table.add_row(
                status_icon,
                title,
                str(paper.year) if paper.year else "-",
                citations,
                source_short,
                str(paper.snowball_iteration),
                key=paper.id
            )

        # Update stats
        stats_panel = self.query_one("#stats-panel", Static)
        stats_panel.update(self._get_stats_text())

    def _get_stats_text(self) -> str:
        """Get statistics text."""
        stats = self.storage.get_statistics()
        total = stats["total"]
        by_status = stats.get("by_status", {})

        included = by_status.get("included", 0)
        excluded = by_status.get("excluded", 0)
        pending = by_status.get("pending", 0)

        return (
            f"[bold]{self.project.name}[/bold] | "
            f"Total: {total} | "
            f"[green]Included: {included}[/green] | "
            f"[red]Excluded: {excluded}[/red] | "
            f"[yellow]Pending: {pending}[/yellow] | "
            f"Iteration: {self.project.current_iteration}"
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        paper_id = event.row_key.value
        paper = self.storage.load_paper(paper_id)

        if paper:
            self.current_paper = paper
            detail_view = self.query_one(PaperDetailView)
            detail_view.update_paper(paper)

    def action_review(self) -> None:
        """Review the selected paper."""
        if not self.current_paper:
            return

        def handle_review(result: Optional[tuple]) -> None:
            if result:
                status_str, notes = result
                status = PaperStatus(status_str)
                self.engine.update_paper_review(
                    self.current_paper.id,
                    status,
                    notes
                )
                self._refresh_table()

                # Reload current paper
                self.current_paper = self.storage.load_paper(self.current_paper.id)
                detail_view = self.query_one(PaperDetailView)
                detail_view.update_paper(self.current_paper)

        self.push_screen(ReviewDialog(self.current_paper), handle_review)

    def action_snowball(self) -> None:
        """Run a snowball iteration."""
        # This would be better as a background task, but for simplicity:
        stats = self.engine.run_snowball_iteration(self.project)
        self.project = self.storage.load_project()
        self._refresh_table()

        # Show notification (in a real app, use a notification widget)
        # For now, just update the stats

    def action_export(self) -> None:
        """Export papers."""
        papers = self.storage.load_all_papers()

        # Export BibTeX
        bibtex_exporter = BibTeXExporter()
        bibtex_content = bibtex_exporter.export(papers, only_included=True)
        bibtex_path = self.project_dir / "export_included.bib"
        with open(bibtex_path, 'w') as f:
            f.write(bibtex_content)

        # Export CSV
        csv_exporter = CSVExporter()
        csv_path = self.project_dir / "export_all.csv"
        csv_exporter.export(papers, csv_path, only_included=False)

        # Update stats to show export completed
        # In a real app, show a notification

    def action_filter(self) -> None:
        """Open filter dialog."""
        # Placeholder for filter dialog
        pass


def run_tui(
    project_dir: Path,
    storage: JSONStorage,
    engine: SnowballEngine,
    project: ReviewProject
) -> None:
    """Run the TUI application."""
    app = SnowballApp(project_dir, storage, engine, project)
    app.run()
