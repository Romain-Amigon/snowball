"""Main TUI application using Textual."""

import webbrowser
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

    TITLE = "Snowball SLR"
    SUB_TITLE = "Systematic Literature Review Tool"

    CSS = """
    /* Color scheme */
    Screen {
        layout: vertical;
        background: #0a0e14;
    }

    /* Stats panel styling */
    #stats-panel {
        height: auto;
        padding: 1;
        border: tall #30363d;
        background: #161b22;
        color: #c9d1d9;
    }

    /* Papers table styling */
    #papers-table {
        height: 1fr;
        width: 100%;
        background: #0d1117;
        border: tall #30363d;
    }

    DataTable > .datatable--header {
        background: #161b22;
        color: #58a6ff;
        text-style: bold;
    }

    DataTable > .datatable--cursor {
        background: #1f6feb 30%;
        color: #ffffff;
    }

    DataTable:focus > .datatable--cursor {
        background: #1f6feb 50%;
    }

    /* Detail section styling */
    #detail-section {
        height: 0;
        max-height: 25;
        width: 100%;
        background: #0d1117;
        border-top: tall #30363d;
        padding: 0;
        overflow-y: auto;
    }

    #detail-section.hidden {
        height: 0;
        padding: 0;
        border: none;
    }

    .detail-content {
        width: 100%;
        height: auto;
        padding: 1 2;
        background: #0d1117;
        color: #c9d1d9;
    }

    /* Review dialog styling */
    #review-dialog {
        width: 70;
        height: 30;
        border: thick #58a6ff;
        background: #161b22;
        padding: 2;
    }

    #review-dialog Label {
        color: #c9d1d9;
        margin: 1 0;
    }

    #review-dialog Select {
        background: #0d1117;
        border: solid #30363d;
        margin: 1 0;
    }

    #review-dialog TextArea {
        background: #0d1117;
        border: solid #30363d;
        height: 8;
        margin: 1 0;
    }

    /* Button styling */
    Button {
        margin: 1;
        background: #21262d;
        color: #c9d1d9;
        border: solid #30363d;
    }

    Button:hover {
        background: #30363d;
        border: solid #58a6ff;
    }

    Button.primary {
        background: #1f6feb;
        color: #ffffff;
        border: none;
    }

    Button.primary:hover {
        background: #388bfd;
    }

    /* Header and Footer */
    Header {
        background: #161b22;
        color: #58a6ff;
        border-bottom: tall #30363d;
    }

    Footer {
        background: #161b22;
        color: #8b949e;
        border-top: tall #30363d;
    }

    Footer > .footer--key {
        background: #21262d;
        color: #58a6ff;
    }

    Footer > .footer--description {
        color: #c9d1d9;
    }

    /* Scrollbar styling */
    ScrollableContainer:focus {
        border: tall #58a6ff 50%;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("i", "include", "Include"),
        Binding("right", "include", "→ Include", show=False),
        Binding("e", "exclude", "Exclude"),
        Binding("left", "exclude", "← Exclude", show=False),
        Binding("m", "maybe", "Maybe"),
        Binding("p", "pending", "Pending"),
        Binding("n", "notes", "Notes"),
        Binding("o", "open", "Open"),
        Binding("s", "snowball", "Snowball"),
        Binding("x", "export", "Export"),
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

        # Sort state tracking
        self.sort_column: str = "Citations"
        self.sort_ascending: bool = False  # False = descending (highest first)
        self.sort_cycle_position: int = 1  # 0=asc, 1=desc, 2=default

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._get_stats_text(), id="stats-panel")
        yield DataTable(id="papers-table", cursor_type="row")

        # Detail section - starts hidden
        detail_section = ScrollableContainer(
            Static("", classes="detail-content"),
            id="detail-section",
            classes="hidden"
        )
        yield detail_section

        yield Footer()

    def _get_column_label(self, column_name: str) -> str:
        """Get column label with sort indicator if applicable."""
        if self.sort_column != column_name or self.sort_cycle_position == 2:
            # Not sorted by this column, or in default state
            return column_name

        # Add sort indicator
        if self.sort_ascending:
            return f"{column_name} ▲"
        else:
            return f"{column_name} ▼"

    def _get_sort_key(self, paper: Paper):
        """Generate sort key for a paper based on current sort column.

        Returns a tuple where the first element controls None/missing value ordering,
        and the second element is the actual value for comparison.
        """
        column = self.sort_column

        if column == "Status":
            # Sort by status value
            status_val = paper.status.value if hasattr(paper.status, 'value') else paper.status
            # Status order: included, excluded, maybe, pending
            status_order = {"included": 0, "excluded": 1, "maybe": 2, "pending": 3}
            return (0, status_order.get(status_val, 999))

        elif column == "Title":
            # Sort alphabetically by title (case-insensitive)
            return (0, paper.title.lower() if paper.title else "zzz")

        elif column == "Year":
            # None years go to the end
            if paper.year is None:
                return (1, 0)  # (1, ...) puts None at end
            return (0, paper.year)

        elif column == "Citations":
            # None citations go to the end
            if paper.citation_count is None:
                return (1, 0)
            return (0, paper.citation_count)

        elif column == "Source":
            # Sort by source value
            source_val = paper.source.value if hasattr(paper.source, 'value') else paper.source
            # Source order: seed, backward, forward
            source_order = {"seed": 0, "backward": 1, "forward": 2}
            return (0, source_order.get(source_val, 999))

        elif column == "Iter":
            # Iteration should never be None
            return (0, paper.snowball_iteration)

        else:
            # Fallback: sort by iteration, then status
            status_val = paper.status.value if hasattr(paper.status, 'value') else paper.status
            return (0, (paper.snowball_iteration, status_val))

    def on_mount(self) -> None:
        """Set up the table when app starts."""
        table = self.query_one("#papers-table", DataTable)

        # Add columns with sort indicators
        table.add_columns(
            self._get_column_label("Status"),
            self._get_column_label("Title"),
            self._get_column_label("Year"),
            self._get_column_label("Citations"),
            self._get_column_label("Source"),
            self._get_column_label("Iter")
        )

        # Load and display papers
        self._refresh_table()

    def _refresh_table(self) -> None:
        """Refresh the papers table."""
        table = self.query_one("#papers-table", DataTable)

        # Clear table including columns to update headers with sort indicators
        table.clear(columns=True)

        # Re-add columns with updated sort indicators
        table.add_columns(
            self._get_column_label("Status"),
            self._get_column_label("Title"),
            self._get_column_label("Year"),
            self._get_column_label("Citations"),
            self._get_column_label("Source"),
            self._get_column_label("Iter")
        )

        papers = self.storage.load_all_papers()

        # Sort papers using current sort settings
        papers.sort(key=self._get_sort_key, reverse=not self.sort_ascending)

        for paper in papers:
            # Status indicator with icon and text
            status_val = paper.status.value if hasattr(paper.status, 'value') else paper.status
            status_display = {
                "included": "[#3fb950]✓ Included[/#3fb950]",
                "excluded": "[#f85149]✗ Excluded[/#f85149]",
                "pending": "[#d29922]? Pending[/#d29922]",
                "maybe": "[#a371f7]~ Maybe[/#a371f7]"
            }.get(status_val, "?")

            # Title (truncate for readability)
            title = paper.title[:160] + "..." if len(paper.title) > 160 else paper.title

            # Citations
            citations = str(paper.citation_count) if paper.citation_count is not None else "-"

            # Source
            source = paper.source.value if hasattr(paper.source, 'value') else paper.source
            source_short = source[0].upper()

            table.add_row(
                status_display,
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
            f"[bold #58a6ff]{self.project.name}[/bold #58a6ff] [dim]│[/dim] "
            f"[bold]Total:[/bold] [#58a6ff]{total}[/#58a6ff] [dim]│[/dim] "
            f"[#3fb950]✓ Included: {included}[/#3fb950] [dim]│[/dim] "
            f"[#f85149]✗ Excluded: {excluded}[/#f85149] [dim]│[/dim] "
            f"[#d29922]? Pending: {pending}[/#d29922] [dim]│[/dim] "
            f"[bold]Iteration:[/bold] [#a371f7]{self.project.current_iteration}[/#a371f7]"
        )

    def _format_paper_details(self, paper: Paper) -> str:
        """Format paper details as rich text."""
        lines = []
        lines.append(f"[bold #58a6ff]{paper.title}[/bold #58a6ff]\n")

        # Authors
        if paper.authors:
            authors_str = ", ".join([a.name for a in paper.authors[:10]])
            if len(paper.authors) > 10:
                authors_str += f" (+{len(paper.authors) - 10} more)"
            lines.append(f"[bold #79c0ff]Authors:[/bold #79c0ff] {authors_str}")

        # Year and venue
        year_venue = []
        if paper.year:
            year_venue.append(str(paper.year))
        if paper.venue and paper.venue.name:
            year_venue.append(paper.venue.name)
        if year_venue:
            lines.append(f"[bold #79c0ff]Published:[/bold #79c0ff] {' - '.join(year_venue)}")

        # Identifiers
        ids = []
        if paper.doi:
            ids.append(f"DOI: {paper.doi}")
        if paper.arxiv_id:
            ids.append(f"arXiv: {paper.arxiv_id}")
        if ids:
            lines.append(f"[bold #79c0ff]IDs:[/bold #79c0ff] {', '.join(ids)}")

        # Metrics
        if paper.citation_count is not None:
            cit_text = f"Citations: {paper.citation_count}"
            if paper.influential_citation_count:
                cit_text += f" (influential: {paper.influential_citation_count})"
            lines.append(f"[bold #79c0ff]Impact:[/bold #79c0ff] {cit_text}")

        # Review info
        status_color = {
            "included": "#3fb950",
            "excluded": "#f85149",
            "pending": "#d29922",
            "maybe": "#a371f7"
        }.get(paper.status.value if hasattr(paper.status, 'value') else paper.status, "#c9d1d9")

        lines.append(f"[bold #79c0ff]Status:[/bold #79c0ff] [{status_color}]{paper.status.value if hasattr(paper.status, 'value') else paper.status}[/{status_color}]")
        lines.append(f"[bold #79c0ff]Source:[/bold #79c0ff] {paper.source.value if hasattr(paper.source, 'value') else paper.source} (iteration {paper.snowball_iteration})")

        # Abstract
        if paper.abstract:
            lines.append(f"\n[bold #79c0ff]Abstract:[/bold #79c0ff]")
            lines.append(paper.abstract)

        # Notes
        if paper.notes:
            lines.append(f"\n[bold #79c0ff]Notes:[/bold #79c0ff]")
            lines.append(paper.notes)

        return "\n".join(lines)

    def _show_paper_details(self, paper: Paper) -> None:
        """Show details for a paper in the detail section."""
        self.current_paper = paper
        details_text = self._format_paper_details(paper)

        # Update the content
        detail_section = self.query_one("#detail-section")
        detail_content = detail_section.query_one(".detail-content")
        detail_content.update(details_text)

        # Show the detail section
        detail_section.remove_class("hidden")
        detail_section.styles.height = "auto"
        detail_section.styles.max_height = 25

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row cursor movement - show details automatically."""
        if event.row_key is None:
            return

        paper_id = event.row_key.value
        paper = self.storage.load_paper(paper_id)

        if paper:
            self._show_paper_details(paper)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection (Enter key) - toggle detail section."""
        paper_id = event.row_key.value
        paper = self.storage.load_paper(paper_id)

        if paper:
            # Check if we're selecting the same paper (toggle off)
            detail_section = self.query_one("#detail-section")
            if self.current_paper and self.current_paper.id == paper.id:
                # Toggle off - hide detail section
                detail_section.add_class("hidden")
                detail_section.styles.height = 0
                self.current_paper = None
            else:
                # Show/update detail section
                self._show_paper_details(paper)

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Handle column header clicks for sorting."""
        # Get clicked column label (strip any existing sort indicators)
        # event.label is a Rich Text object, convert to string first
        clicked_column = str(event.label).replace(" ▲", "").replace(" ▼", "")

        # Determine next state in the cycle
        if self.sort_column == clicked_column:
            # Same column clicked - advance through cycle
            self.sort_cycle_position = (self.sort_cycle_position + 1) % 3

            if self.sort_cycle_position == 0:
                # First click: ascending
                self.sort_ascending = True
            elif self.sort_cycle_position == 1:
                # Second click: descending
                self.sort_ascending = False
            else:
                # Third click: reset to default (Citations descending)
                self.sort_column = "Citations"
                self.sort_ascending = False
                self.sort_cycle_position = 1
        else:
            # Different column clicked - start fresh at ascending
            self.sort_column = clicked_column
            self.sort_ascending = True
            self.sort_cycle_position = 0

        # Refresh table with new sort
        self._refresh_table()

    def _update_paper_status(self, status: PaperStatus) -> None:
        """Update the status of the currently selected paper and move to next."""
        if not self.current_paper:
            return

        # Get the current table and find next paper
        table = self.query_one("#papers-table", DataTable)
        current_row_index = table.cursor_row

        # Update the paper status
        self.engine.update_paper_review(
            self.current_paper.id,
            status,
            self.current_paper.notes  # Keep existing notes
        )

        # Refresh the table to show updated status
        self._refresh_table()

        # Move to the next paper (or stay at current if at end)
        table = self.query_one("#papers-table", DataTable)
        if table.row_count > 0:
            # Move to next row, or stay at last if we're at the end
            next_row = min(current_row_index + 1, table.row_count - 1)
            table.move_cursor(row=next_row)

            # The move_cursor will trigger on_data_table_row_highlighted
            # which will show the details automatically

    def action_include(self) -> None:
        """Mark the selected paper as included."""
        self._update_paper_status(PaperStatus.INCLUDED)

    def action_exclude(self) -> None:
        """Mark the selected paper as excluded."""
        self._update_paper_status(PaperStatus.EXCLUDED)

    def action_maybe(self) -> None:
        """Mark the selected paper as maybe."""
        self._update_paper_status(PaperStatus.MAYBE)

    def action_pending(self) -> None:
        """Mark the selected paper as pending."""
        self._update_paper_status(PaperStatus.PENDING)

    def action_notes(self) -> None:
        """Add/edit notes for the selected paper."""
        if not self.current_paper:
            return

        # Use the ReviewDialog just for notes editing
        def handle_notes(result: Optional[tuple]) -> None:
            if result:
                _, notes = result
                self.engine.update_paper_review(
                    self.current_paper.id,
                    self.current_paper.status,  # Keep existing status
                    notes
                )
                self._refresh_table()

                # Reload current paper and update detail section
                self.current_paper = self.storage.load_paper(self.current_paper.id)
                if self.current_paper:
                    detail_section = self.query_one("#detail-section")
                    if not detail_section.has_class("hidden"):
                        details_text = self._format_paper_details(self.current_paper)
                        detail_content = detail_section.query_one(".detail-content")
                        detail_content.update(details_text)

        self.push_screen(ReviewDialog(self.current_paper), handle_notes)

    def action_open(self) -> None:
        """Open the paper's DOI or arXiv URL in browser."""
        if not self.current_paper:
            return

        # Prefer DOI, fallback to arXiv
        url = None
        if self.current_paper.doi:
            url = f"https://doi.org/{self.current_paper.doi}"
        elif self.current_paper.arxiv_id:
            url = f"https://arxiv.org/abs/{self.current_paper.arxiv_id}"

        if url:
            webbrowser.open(url)

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
