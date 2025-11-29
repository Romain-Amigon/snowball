"""Example usage of Snowball SLR programmatically."""

from pathlib import Path
from snowball import (
    ReviewProject,
    FilterCriteria,
    JSONStorage,
    APIAggregator,
    SnowballEngine,
    PaperStatus,
)

def main():
    """Example workflow for programmatic usage."""

    # 1. Set up a project
    project_dir = Path("example-slr")
    storage = JSONStorage(project_dir)

    # Create a new project
    project = ReviewProject(
        name="Example Literature Review",
        description="A demonstration of the Snowball SLR tool",
        max_iterations=1,
        filter_criteria=FilterCriteria(
            min_year=2018,
            max_year=2024,
            min_citations=10
        )
    )

    # Save the project
    storage.save_project(project)
    print(f"Created project: {project.name}")

    # 2. Set up the engine
    api = APIAggregator(
        # Add your API key here for better rate limits
        # s2_api_key="your-key-here",
        email="your.email@example.com"
    )

    engine = SnowballEngine(storage, api)

    # 3. Add a seed paper by DOI
    print("\nAdding seed paper...")
    seed_doi = "10.1038/s41586-021-03819-2"  # Example: AlphaFold 2 paper
    paper = engine.add_seed_from_doi(seed_doi, project)

    if paper:
        print(f"Added: {paper.title}")
        print(f"Authors: {', '.join([a.name for a in paper.authors[:3]])}...")
        print(f"Year: {paper.year}")
        print(f"Citations: {paper.citation_count}")
    else:
        print("Failed to add seed paper. Check the DOI or your internet connection.")
        return

    # 4. Run snowballing (this will take some time)
    print("\nRunning snowball iteration...")
    stats = engine.run_snowball_iteration(project)

    print(f"\nIteration complete!")
    print(f"  Discovered: {stats['added']} papers")
    print(f"  Backward (references): {stats['backward']}")
    print(f"  Forward (citations): {stats['forward']}")
    print(f"  Auto-excluded: {stats['auto_excluded']}")
    print(f"  For review: {stats['for_review']}")

    # 5. Review some papers (example: auto-include highly cited papers)
    print("\nAuto-reviewing papers...")
    papers_for_review = engine.get_papers_for_review()

    auto_included = 0
    for paper in papers_for_review[:10]:  # Review first 10
        # Simple rule: include if citations > 100
        if paper.citation_count and paper.citation_count > 100:
            engine.update_paper_review(
                paper.id,
                PaperStatus.INCLUDED,
                "Auto-included: high citation count"
            )
            auto_included += 1
            print(f"  Included: {paper.title[:60]}...")

    print(f"\nAuto-included {auto_included} papers")

    # 6. View statistics
    stats = storage.get_statistics()
    print(f"\nProject statistics:")
    print(f"  Total papers: {stats['total']}")
    print(f"  By status: {stats['by_status']}")
    print(f"  By source: {stats['by_source']}")

    # 7. Export results
    print(f"\nTo export results, run:")
    print(f"  snowball export {project_dir} --format all")
    print(f"\nTo launch the interactive review interface, run:")
    print(f"  snowball review {project_dir}")


if __name__ == "__main__":
    main()
