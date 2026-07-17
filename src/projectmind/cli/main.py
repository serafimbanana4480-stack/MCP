"""ProjectMind command-line interface.

Provides ``init``, ``index``, ``status``, ``doctor``, memory, graph, and
dashboard commands built on top of the shared :class:`AppContext`.
"""

from __future__ import annotations

import json
import webbrowser
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from projectmind import __version__
from projectmind.app import AppContext
from projectmind.config import ProjectMindSettings
from projectmind.execution.internal_state import initialize_project_state
from projectmind.server import run_server

app = typer.Typer(
    name="projectmind",
    help="ProjectMind: a local-first MCP server for engineering context.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _ctx(root: Path | None = None) -> AppContext:
    return AppContext.create(root)


def _load_settings(root: Path | None = None) -> ProjectMindSettings:
    _, settings = ProjectMindSettings.load(root)
    return settings


@app.command()
def version() -> None:
    """Print the installed ProjectMind version."""

    console.print(f"projectmind {__version__}")


@app.command()
def init(
    root: Path = typer.Argument(Path("."), help="Project root to initialize."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config.toml."),
) -> None:
    """Create the `.projectmind` state directory, config, and database."""

    result = initialize_project_state(root, overwrite_config=force)
    console.print("[green]Initialized ProjectMind[/green]")
    for key, value in result.items():
        console.print(f"  {key}: {value}")


@app.command()
def index(
    path: Path = typer.Argument(Path("."), help="Scope to index."),
    root: Path = typer.Option(None, "--root", help="Project root."),
) -> None:
    """Index a scope and print the resulting graph summary."""

    context = _ctx(root)
    summary = context.indexer.index_scope(path)
    console.print(
        f"[green]Indexed[/green] {summary.files} files, "
        f"{summary.nodes} nodes, {summary.edges} edges."
    )


@app.command()
def status(
    root: Path = typer.Option(None, "--root", help="Project root."),
) -> None:
    """Print local index, memory, plan, and telemetry counts."""

    context = _ctx(root)
    tables = {
        "workspaces": "workspaces",
        "files": "files",
        "nodes": "nodes",
        "edges": "edges",
        "memories": "memories",
        "plans": "plans",
        "telemetry_events": "telemetry_events",
    }
    table = Table(title="ProjectMind status")
    table.add_column("metric")
    table.add_column("count")
    with context.database.connect() as connection:
        for key, table_name in tables.items():
            count = int(connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])
            table.add_row(key, str(count))
    console.print(table)


@app.command()
def doctor(
    root: Path = typer.Option(None, "--root", help="Project root."),
) -> None:
    """Run local environment and configuration sanity checks."""

    problems: list[str] = []
    settings = _load_settings(root)
    if settings.embeddings.provider not in {"disabled", "local", "openai", "voyage"}:
        problems.append("embeddings.provider is invalid")
    weights_total = sum(settings.retrieval.scoring_weights.model_dump().values())
    if abs(weights_total - 1.0) > 1e-8:
        problems.append(
            f"retrieval scoring weights must sum to 1.0, got {weights_total:.8f}"
        )
    try:
        context = _ctx(root)
        context.database.connect().close()
    except Exception as exc:  # pragma: no cover - defensive
        problems.append(f"database connection failed: {exc}")

    if problems:
        console.print("[red]Doctor found issues:[/red]")
        for problem in problems:
            console.print(f"  - {problem}")
        raise typer.Exit(code=1)
    console.print("[green]Doctor: all checks passed[/green]")


@app.command()
def memory(
    action: str = typer.Argument(..., help="search | export | import"),
    query: str = typer.Argument("", help="Search query or file path."),
    root: Path = typer.Option(None, "--root", help="Project root."),
    limit: int = typer.Option(20, "--limit", help="Search result limit."),
) -> None:
    """Search, export, or import local memory."""

    context = _ctx(root)
    if action == "search":
        results = context.memory.search(query, limit=limit)
        for result in results:
            console.print(f"{result.entry.id} ({result.score:.2f}) {result.entry.content[:80]}")
    elif action == "export":
        target = context.memory.export_memory(query or "memory.json")
        console.print(f"[green]Exported to[/green] {target}")
    elif action == "import":
        entries = context.memory.import_memory(query)
        console.print(f"[green]Imported[/green] {len(entries)} entries")
    else:
        console.print(f"[red]Unknown memory action:[/red] {action}")
        raise typer.Exit(code=1)


@app.command()
def graph(
    action: str = typer.Argument(..., help="impact | cycles | export"),
    target: str = typer.Argument("", help="Node id, diff, or scope."),
    root: Path = typer.Option(None, "--root", help="Project root."),
    format: str = typer.Option("mermaid", "--format", help="Diagram format."),
) -> None:
    """Run graph analyses or export a diagram."""

    context = _ctx(root)
    if action == "impact":
        result = context.graph_analyzer.impact_analysis(target)
        console.print(json.dumps(result.model_dump(mode="json"), indent=2))
    elif action == "cycles":
        cycles = context.graph_analyzer.detect_dependency_cycles(scope=target or ".")
        console.print(json.dumps(cycles, indent=2))
    elif action == "export":
        console.print(context.diagrams.export(scope=target or ".", format=format))
    else:
        console.print(f"[red]Unknown graph action:[/red] {action}")
        raise typer.Exit(code=1)


@app.command()
def dashboard(
    root: Path = typer.Option(None, "--root", help="Project root."),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host."),
    port: int = typer.Option(8787, "--port", help="Bind port."),
    open_browser: bool = typer.Option(True, "--no-open", flag_value=False, help="Open browser."),
) -> None:
    """Start the ProjectMind dashboard (HTTP server)."""

    settings = _load_settings(root)
    settings.dashboard.enabled = True
    settings.dashboard.host = host
    settings.dashboard.port = port
    if open_browser:
        webbrowser.open(f"http://{host}:{port}")
    console.print(f"[green]Dashboard starting at[/green] http://{host}:{port}")
    # The dashboard is served by the streamable-http MCP transport.
    from projectmind.server import run_server

    run_server(root, transport="streamable-http", host=host, port=port)


@app.command()
def config(
    action: str = typer.Argument("validate", help="validate | show"),
    root: Path = typer.Option(None, "--root", help="Project root."),
) -> None:
    """Validate or print the resolved configuration."""

    settings = _load_settings(root)
    if action == "validate":
        console.print("[green]Configuration is valid[/green]")
    elif action == "show":
        console.print(settings.model_dump_json(indent=2))
    else:
        console.print(f"[red]Unknown config action:[/red] {action}")
        raise typer.Exit(code=1)


@app.command()
def serve(
    root: Path = typer.Option(None, "--root", help="Project root to serve."),
    transport: str = typer.Option(
        "stdio", "--transport", help="stdio | streamable-http"
    ),
    profile: str = typer.Option("full", "--profile", help="Tool profile."),
    host: str = typer.Option("127.0.0.1", "--host", help="HTTP host."),
    port: int = typer.Option(8787, "--port", help="HTTP port."),
    http_token: str = typer.Option(None, "--http-token", help="Bearer token for HTTP."),
) -> None:
    """Run the ProjectMind MCP server."""

    run_server(
        root,
        transport=transport,
        profile=profile,
        host=host,
        port=port,
        http_token=http_token,
    )


if __name__ == "__main__":
    app()
