"""Command-line interface for Movie Conceptualizer."""

import asyncio
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

app = typer.Typer(
    name="moviecon",
    help="AI-powered filmmaking platform: script → shot list → storyboard",
    add_completion=False,
)
db_app = typer.Typer(help="Database maintenance commands.")
app.add_typer(db_app, name="db")
console = Console()


@app.command()
def parse(
    script_path: Path = typer.Argument(..., help="Path to screenplay file (.fountain)"),
    output: Path | None = typer.Option(None, "-o", "--output", help="Output JSON file"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Show detailed output"),
) -> None:
    """Parse a screenplay file and extract structure."""
    from movie_conceptualizer.parsers import get_script_summary, load_script, validate_script

    if not script_path.exists():
        console.print(f"[red]Error:[/red] File not found: {script_path}")
        raise typer.Exit(1)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Parsing screenplay...", total=None)
        script = load_script(str(script_path))

    # Display summary
    summary = get_script_summary(script)
    warnings = validate_script(script)

    table = Table(title=f"📽️  {script.title or 'Untitled'}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Scenes", str(summary["scene_count"]))
    table.add_row("Characters", str(summary["character_count"]))
    table.add_row("Locations", str(summary["location_count"]))
    table.add_row("Est. Pages", f"{summary['total_pages']:.1f}")
    table.add_row("Est. Runtime", f"{summary['estimated_runtime_minutes']:.0f} min")

    console.print(table)

    if warnings:
        console.print("\n[yellow]Warnings:[/yellow]")
        for warning in warnings:
            console.print(f"  • {warning}")

    if verbose:
        console.print("\n[bold]Scenes:[/bold]")
        for scene in script.scenes:
            console.print(f"  {scene.scene_number}. {scene.heading}")

        console.print("\n[bold]Characters:[/bold]")
        for char in script.characters:
            console.print(f"  • {char.name} ({char.dialogue_count} lines)")

    if output:
        output.write_text(script.model_dump_json(indent=2))
        console.print(f"\n[green]✓[/green] Saved to {output}")


@db_app.command("status")
def db_status() -> None:
    """Show current database schema version."""
    from movie_conceptualizer.storage import create_database

    async def _run() -> None:
        db = create_database()
        version = await db.get_schema_version()
        console.print(f"[green]Schema version:[/green] {version}")
        await db.close()

    asyncio.run(_run())


@db_app.command("migrate")
def db_migrate() -> None:
    """Run database migrations."""
    from movie_conceptualizer.storage import init_database

    async def _run() -> None:
        db = await init_database()
        version = await db.get_schema_version()
        console.print(f"[green]Database migrated to version:[/green] {version}")
        await db.close()

    asyncio.run(_run())


@db_app.command("backup")
def db_backup(
    output: Path | None = typer.Option(
        None, "-o", "--output", help="Output path for SQLite backup file"
    ),
) -> None:
    """Backup the SQLite database file."""
    from movie_conceptualizer.storage.database import (
        DatabaseBackend,
        get_database_backend,
        get_database_path,
    )

    backend = get_database_backend()
    if backend != DatabaseBackend.SQLITE:
        console.print("[red]Error:[/red] Backup is only supported for SQLite.")
        raise typer.Exit(1)

    db_path = get_database_path()
    if not db_path.exists():
        console.print(f"[red]Error:[/red] Database file not found: {db_path}")
        raise typer.Exit(1)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = output or db_path.with_name(f"{db_path.stem}_backup_{timestamp}{db_path.suffix}")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, backup_path)
    console.print(f"[green]Backup created:[/green] {backup_path}")


@app.command()
def analyze(
    script_path: Path = typer.Argument(..., help="Path to screenplay file"),
    output: Path | None = typer.Option(None, "-o", "--output", help="Output JSON file"),
    model: str = typer.Option("claude-sonnet-4-20250514", "-m", "--model", help="LLM model to use"),
) -> None:
    """Analyze a screenplay with AI to extract emotional beats and visual opportunities."""
    from movie_conceptualizer.agents import ScriptAnalyzerAgent
    from movie_conceptualizer.parsers import load_script

    if not script_path.exists():
        console.print(f"[red]Error:[/red] File not found: {script_path}")
        raise typer.Exit(1)

    script = load_script(str(script_path))
    console.print(f"[bold]Analyzing:[/bold] {script.title or 'Untitled'}")

    agent = ScriptAnalyzerAgent(model_name=model)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Analyzing scenes...", total=len(script.scenes))

        analyzed_scenes = []
        for scene in script.scenes:
            result = agent.analyze_scene(scene)
            analyzed_scenes.append(result)
            progress.advance(task)

    # Display results
    console.print("\n[bold green]✓ Analysis Complete[/bold green]\n")

    for analyzed in analyzed_scenes:
        panel_content = f"""[cyan]Tone:[/cyan] {analyzed.overall_tone.value}
[cyan]Pacing:[/cyan] {analyzed.pacing.value}
[cyan]Emotional Beats:[/cyan] {len(analyzed.emotional_beats)}
[cyan]Summary:[/cyan] {analyzed.summary}
[cyan]Atmosphere:[/cyan] {analyzed.scene_atmosphere or 'N/A'}"""

        console.print(Panel(
            panel_content,
            title=f"Scene {analyzed.scene_number}: {analyzed.scene_heading[:50]}",
            border_style="blue",
        ))

    if output:
        output_data = {"scenes": [s.model_dump() for s in analyzed_scenes]}
        output.write_text(json.dumps(output_data, indent=2, default=str))
        console.print(f"\n[green]✓[/green] Saved to {output}")


@app.command()
def shots(
    script_path: Path = typer.Argument(..., help="Path to screenplay file"),
    output: Path | None = typer.Option(None, "-o", "--output", help="Output JSON file"),
    model: str = typer.Option("claude-sonnet-4-20250514", "-m", "--model", help="LLM model to use"),
) -> None:
    """Generate shot lists from a screenplay."""
    from movie_conceptualizer.agents import ScriptAnalyzerAgent, ShotDesignerAgent
    from movie_conceptualizer.parsers import load_script

    if not script_path.exists():
        console.print(f"[red]Error:[/red] File not found: {script_path}")
        raise typer.Exit(1)

    script = load_script(str(script_path))
    console.print(f"[bold]Generating shots for:[/bold] {script.title or 'Untitled'}")

    analyzer = ScriptAnalyzerAgent(model_name=model)
    shot_designer = ShotDesignerAgent(model_name=model)

    all_shot_lists = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Processing scenes...", total=len(script.scenes))

        for scene in script.scenes:
            # First analyze
            analyzed = analyzer.analyze_scene(scene)
            # Then design shots
            shot_list = shot_designer.design_shot_list(analyzed)
            all_shot_lists.append(shot_list)
            progress.advance(task)

    # Display results
    console.print("\n[bold green]✓ Shot Lists Generated[/bold green]\n")

    total_shots = sum(len(sl.shots) for sl in all_shot_lists)
    console.print(f"[bold]Total Shots:[/bold] {total_shots}\n")

    for shot_list in all_shot_lists:
        table = Table(title=f"Scene {shot_list.scene_number}")
        table.add_column("#", style="dim", width=4)
        table.add_column("Type", style="cyan", width=15)
        table.add_column("Movement", style="yellow", width=12)
        table.add_column("Description", style="white")

        for shot in shot_list.shots:
            movement = shot.camera_movement.value if hasattr(shot.camera_movement, 'value') else (shot.camera_movement or "STATIC")
            shot_type = shot.shot_type.value if hasattr(shot.shot_type, 'value') else shot.shot_type
            table.add_row(
                str(shot.shot_number),
                shot_type,
                movement,
                shot.description[:60] + "..." if len(shot.description) > 60 else shot.description,
            )

        console.print(table)
        console.print()

    if output:
        output_data = {"shot_lists": [sl.model_dump() for sl in all_shot_lists]}
        output.write_text(json.dumps(output_data, indent=2, default=str))
        console.print(f"[green]✓[/green] Saved to {output}")


@app.command()
def storyboard(
    script_path: Path = typer.Argument(..., help="Path to screenplay file"),
    output: Path | None = typer.Option(None, "-o", "--output", help="Output JSON file"),
    model: str = typer.Option("claude-sonnet-4-20250514", "-m", "--model", help="LLM model to use"),
    style: str = typer.Option("cinematic", "-s", "--style", help="Visual style for prompts"),
) -> None:
    """Generate storyboard image prompts from a screenplay."""
    from movie_conceptualizer.agents import (
        ScriptAnalyzerAgent,
        ShotDesignerAgent,
        StoryboardArtistAgent,
    )
    from movie_conceptualizer.parsers import load_script

    if not script_path.exists():
        console.print(f"[red]Error:[/red] File not found: {script_path}")
        raise typer.Exit(1)

    script = load_script(str(script_path))
    console.print(f"[bold]Generating storyboard for:[/bold] {script.title or 'Untitled'}")
    console.print(f"[dim]Style: {style}[/dim]\n")

    analyzer = ScriptAnalyzerAgent(model_name=model)
    shot_designer = ShotDesignerAgent(model_name=model)
    storyboard_artist = StoryboardArtistAgent(model_name=model)

    all_frames = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Processing scenes...", total=len(script.scenes))

        for scene in script.scenes:
            analyzed = analyzer.analyze_scene(scene)
            shot_list = shot_designer.design_shot_list(analyzed)
            storyboard = storyboard_artist.create_storyboard_for_scene(
                shot_list, analyzed, style_guide=style
            )
            all_frames.extend(storyboard.frames)
            progress.advance(task)

    # Display results
    console.print("\n[bold green]✓ Storyboard Prompts Generated[/bold green]\n")
    console.print(f"[bold]Total Frames:[/bold] {len(all_frames)}\n")

    for i, frame in enumerate(all_frames[:10], 1):  # Show first 10
        console.print(Panel(
            frame.image_prompt,
            title=f"Frame {i}: Shot {frame.shot_id}",
            border_style="magenta",
        ))

    if len(all_frames) > 10:
        console.print(f"\n[dim]... and {len(all_frames) - 10} more frames[/dim]")

    if output:
        output_data = {"frames": [f.model_dump() for f in all_frames]}
        output.write_text(json.dumps(output_data, indent=2, default=str))
        console.print(f"\n[green]✓[/green] Saved to {output}")


@app.command()
def pipeline(
    script_path: Path = typer.Argument(..., help="Path to screenplay file"),
    output_dir: Path = typer.Option(Path("./output"), "-o", "--output", help="Output directory"),
    model: str = typer.Option("claude-sonnet-4-20250514", "-m", "--model", help="LLM model to use"),
    style: str = typer.Option("cinematic", "-s", "--style", help="Visual style"),
) -> None:
    """Run the full pipeline: parse → analyze → shots → storyboard."""
    from movie_conceptualizer.parsers import load_script
    from movie_conceptualizer.workflows import PipelineConfig, run_pipeline

    if not script_path.exists():
        console.print(f"[red]Error:[/red] File not found: {script_path}")
        raise typer.Exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    script = load_script(str(script_path))

    console.print(Panel(
        f"[bold]{script.title or 'Untitled'}[/bold]\n\n"
        f"Scenes: {len(script.scenes)}\n"
        f"Characters: {len(script.characters)}\n"
        f"Model: {model}\n"
        f"Style: {style}",
        title="🎬 Movie Conceptualizer Pipeline",
        border_style="green",
    ))

    config = PipelineConfig(
        model_name=model,
        style_guide=style,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Running AI pipeline...", total=None)
        result = run_pipeline(script, config)

    # Save outputs
    script_output = output_dir / "script.json"
    script_output.write_text(script.model_dump_json(indent=2))

    if result.analyzed_scenes:
        analysis_output = output_dir / "analysis.json"
        analysis_data = [s.model_dump() for s in result.analyzed_scenes]
        analysis_output.write_text(json.dumps(analysis_data, indent=2, default=str))

    if result.shot_lists:
        shots_output = output_dir / "shots.json"
        shots_data = [sl.model_dump() for sl in result.shot_lists]
        shots_output.write_text(json.dumps(shots_data, indent=2, default=str))

    if result.storyboards:
        storyboard_output = output_dir / "storyboard.json"
        frames_data = []
        for sb in result.storyboards:
            frames_data.extend([f.model_dump() for f in sb.frames])
        storyboard_output.write_text(json.dumps(frames_data, indent=2, default=str))

    # Display summary
    console.print("\n[bold green]✓ Pipeline Complete[/bold green]\n")

    table = Table(title="Results Summary")
    table.add_column("Output", style="cyan")
    table.add_column("Count", style="green")
    table.add_column("File", style="dim")

    table.add_row("Scenes Analyzed", str(result.scenes_processed), "analysis.json")
    table.add_row("Shots Generated", str(result.total_shots), "shots.json")
    table.add_row("Storyboard Frames", str(result.total_frames), "storyboard.json")

    console.print(table)
    console.print(f"\n[dim]Output directory: {output_dir.absolute()}[/dim]")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
) -> None:
    """Start the API server."""
    import uvicorn

    console.print(Panel(
        f"Starting server at [bold]http://{host}:{port}[/bold]\n\n"
        f"API docs: http://{host}:{port}/docs\n"
        f"Health: http://{host}:{port}/health",
        title="🎬 Movie Conceptualizer API",
        border_style="green",
    ))

    uvicorn.run(
        "movie_conceptualizer.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command()
def version() -> None:
    """Show version information."""
    console.print("[bold]Movie Conceptualizer[/bold] v0.1.0")
    console.print("AI-powered filmmaking: script → shot list → storyboard")


def main() -> None:
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
