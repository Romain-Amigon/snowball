"""Command-line interface for Snowball SLR tool."""

import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
import argparse

from .models import ReviewProject, FilterCriteria
from .storage.json_storage import JSONStorage
from .apis.aggregator import APIAggregator
from .parsers.pdf_parser import PDFParser
from .snowballing import SnowballEngine
from .tui.app import run_tui
from .exporters.bibtex import BibTeXExporter
from .exporters.csv_exporter import CSVExporter


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def init_project(args) -> None:
    """Initialize a new SLR project."""
    project_dir = Path(args.directory)

    if project_dir.exists() and any(project_dir.iterdir()):
        logger.error(f"Directory {project_dir} already exists and is not empty")
        sys.exit(1)

    project_dir.mkdir(parents=True, exist_ok=True)

    # Create storage
    storage = JSONStorage(project_dir)

    # Create project
    project = ReviewProject(
        name=args.name or project_dir.name,
        description=args.description or "",
        max_iterations=args.max_iterations or 1,
    )

    # Set up filters if provided
    if args.min_year or args.max_year:
        project.filter_criteria = FilterCriteria(
            min_year=args.min_year,
            max_year=args.max_year
        )

    # Save project
    storage.save_project(project)

    logger.info(f"Initialized project '{project.name}' in {project_dir}")
    logger.info(f"Max iterations: {project.max_iterations}")


def add_seed(args) -> None:
    """Add seed paper(s) to the project."""
    project_dir = Path(args.directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        sys.exit(1)

    # Load project
    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        sys.exit(1)

    # Set up API and engine
    api = APIAggregator(
        s2_api_key=args.s2_api_key,
        email=args.email
    )
    pdf_parser = PDFParser(use_grobid=not args.no_grobid)
    engine = SnowballEngine(storage, api, pdf_parser)

    # Add seeds
    added_count = 0

    if args.pdf:
        for pdf_path in args.pdf:
            pdf_file = Path(pdf_path)
            if not pdf_file.exists():
                logger.warning(f"PDF not found: {pdf_file}")
                continue

            paper = engine.add_seed_from_pdf(pdf_file, project)
            if paper:
                logger.info(f"Added seed: {paper.title}")
                added_count += 1

    if args.doi:
        for doi in args.doi:
            paper = engine.add_seed_from_doi(doi, project)
            if paper:
                logger.info(f"Added seed: {paper.title}")
                added_count += 1

    logger.info(f"Added {added_count} seed paper(s)")


def run_snowball(args) -> None:
    """Run snowballing iterations."""
    project_dir = Path(args.directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        sys.exit(1)

    # Load project
    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        sys.exit(1)

    # Set up API and engine
    api = APIAggregator(
        s2_api_key=args.s2_api_key,
        email=args.email
    )
    engine = SnowballEngine(storage, api)

    # Run iterations
    iteration_count = 0
    while engine.should_continue_snowballing(project):
        logger.info(f"\nRunning snowball iteration {project.current_iteration + 1}...")

        stats = engine.run_snowball_iteration(project)

        logger.info(f"Iteration {project.current_iteration} complete:")
        logger.info(f"  - Discovered: {stats['added']} papers")
        logger.info(f"  - Backward: {stats['backward']}")
        logger.info(f"  - Forward: {stats['forward']}")
        logger.info(f"  - Auto-excluded: {stats['auto_excluded']}")
        logger.info(f"  - For review: {stats['for_review']}")

        # Reload project
        project = storage.load_project()
        iteration_count += 1

        if args.iterations and iteration_count >= args.iterations:
            break

    logger.info(f"\nSnowballing complete. Ran {iteration_count} iteration(s).")

    # Show summary
    summary = storage.get_statistics()
    logger.info(f"\nProject summary:")
    logger.info(f"  Total papers: {summary['total']}")
    logger.info(f"  By status: {summary['by_status']}")


def review(args) -> None:
    """Launch the interactive review interface."""
    project_dir = Path(args.directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        sys.exit(1)

    # Load project
    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        sys.exit(1)

    # Set up API and engine
    api = APIAggregator(
        s2_api_key=args.s2_api_key,
        email=args.email
    )
    engine = SnowballEngine(storage, api)

    # Launch TUI
    run_tui(project_dir, storage, engine, project)


def export_results(args) -> None:
    """Export results to various formats."""
    project_dir = Path(args.directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        sys.exit(1)

    # Load project and papers
    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found.")
        sys.exit(1)

    papers = storage.load_all_papers()

    if not papers:
        logger.warning("No papers to export")
        return

    output_dir = Path(args.output) if args.output else project_dir

    # Export BibTeX
    if args.format in ["bibtex", "all"]:
        bibtex_exporter = BibTeXExporter()

        if args.included_only:
            bibtex_content = bibtex_exporter.export(papers, only_included=True)
            bibtex_path = output_dir / "included_papers.bib"
        else:
            bibtex_content = bibtex_exporter.export(papers, only_included=False)
            bibtex_path = output_dir / "all_papers.bib"

        with open(bibtex_path, 'w') as f:
            f.write(bibtex_content)

        logger.info(f"Exported BibTeX to {bibtex_path}")

    # Export CSV
    if args.format in ["csv", "all"]:
        csv_exporter = CSVExporter()

        if args.included_only:
            csv_path = output_dir / "included_papers.csv"
            csv_exporter.export(papers, csv_path, only_included=True)
        else:
            csv_path = output_dir / "all_papers.csv"
            csv_exporter.export(papers, csv_path, only_included=False, include_all_fields=True)

        logger.info(f"Exported CSV to {csv_path}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Snowball - Systematic Literature Review using Snowballing"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize a new SLR project")
    init_parser.add_argument("directory", help="Project directory")
    init_parser.add_argument("--name", help="Project name")
    init_parser.add_argument("--description", help="Project description")
    init_parser.add_argument("--max-iterations", type=int, default=1, help="Maximum snowball iterations")
    init_parser.add_argument("--min-year", type=int, help="Minimum publication year")
    init_parser.add_argument("--max-year", type=int, help="Maximum publication year")

    # Add seed command
    seed_parser = subparsers.add_parser("add-seed", help="Add seed paper(s)")
    seed_parser.add_argument("directory", help="Project directory")
    seed_parser.add_argument("--pdf", nargs="+", help="Path(s) to seed PDF file(s)")
    seed_parser.add_argument("--doi", nargs="+", help="DOI(s) of seed paper(s)")
    seed_parser.add_argument("--s2-api-key", help="Semantic Scholar API key")
    seed_parser.add_argument("--email", help="Email for API polite pools")
    seed_parser.add_argument("--no-grobid", action="store_true", help="Don't use GROBID for PDF parsing")

    # Snowball command
    snowball_parser = subparsers.add_parser("snowball", help="Run snowballing iterations")
    snowball_parser.add_argument("directory", help="Project directory")
    snowball_parser.add_argument("--iterations", type=int, help="Number of iterations to run")
    snowball_parser.add_argument("--s2-api-key", help="Semantic Scholar API key")
    snowball_parser.add_argument("--email", help="Email for API polite pools")

    # Review command
    review_parser = subparsers.add_parser("review", help="Launch interactive review interface")
    review_parser.add_argument("directory", help="Project directory")
    review_parser.add_argument("--s2-api-key", help="Semantic Scholar API key")
    review_parser.add_argument("--email", help="Email for API polite pools")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export results")
    export_parser.add_argument("directory", help="Project directory")
    export_parser.add_argument("--format", choices=["bibtex", "csv", "all"], default="all", help="Export format")
    export_parser.add_argument("--output", help="Output directory")
    export_parser.add_argument("--included-only", action="store_true", help="Only export included papers")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Dispatch to appropriate handler
    if args.command == "init":
        init_project(args)
    elif args.command == "add-seed":
        add_seed(args)
    elif args.command == "snowball":
        run_snowball(args)
    elif args.command == "review":
        review(args)
    elif args.command == "export":
        export_results(args)


if __name__ == "__main__":
    main()
