"""CLI command implementations for the Prompt Library.

Uses Click to define commands that wrap the SQLite-backed storage and search
functions. All existing commands maintain identical output format.
"""

import os
from pathlib import Path
from typing import Optional

import click

from pl.database import get_connection, init_db, close_connection
from pl.renderer import render_prompt
from pl.search import search_prompts
from pl.storage import (
    add_prompt as storage_add,
    delete_prompt,
    get_categories,
    get_info,
    get_prompt,
    import_yaml,
    export_yaml,
    list_prompts,
    optimize as storage_optimize,
)
from pl.models import Prompt


# Global option for database path
def _resolve_db_path(db_arg: Optional[str]) -> Optional[str | Path]:
    """Resolve the --db argument to a path or None for default."""
    if db_arg:
        return Path(db_arg)
    return None


@click.group()
@click.option("--db", default=None, envvar="PROMPT_LIBRARY_DB",
              help="Path to SQLite database (default: XDG data home).",
              hidden=False)
@click.pass_context
def cli(ctx: click.Context, db: Optional[str]) -> None:
    """Prompt Library — manage and use reusable prompt templates.

    Powered by SQLite with FTS5 full-text search for fast, deterministic
    local storage.
    """
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = _resolve_db_path(db)



def _ensure_db(ctx):
    """Initialize the database if it hasn't been initialized yet."""
    db_path = ctx.obj.get("db_path")
    conn = get_connection(db_path)
    init_db(conn)
    return conn


# ── Existing Commands ──────────────────────────────────────────────────────

@cli.command(name="list")
@click.option("--category", "-c", default=None, help="Filter by category name.")
@click.pass_context
def list_cmd(ctx, category: str) -> None:
    """List all prompts, optionally filtered by category."""
    _ensure_db(ctx)
    prompts = list_prompts(category)

    if not prompts:
        msg = "No prompts found."
        if category:
            msg += f" Category '{category}' has no prompts."
        click.echo(msg)
        return

    click.echo(f"{'ID':<30} {'Title':<40} {'Category':<15} Tags")
    click.echo("-" * 100)
    for p in prompts:
        tags_str = ", ".join(p.tags) if p.tags else ""
        click.echo(f"{p.id:<30} {p.title:<40} {p.category:<15} {tags_str}")
    click.echo(f"\n{len(prompts)} prompt(s) found.")


@cli.command()
@click.argument("query")
@click.option("--category", "-c", default=None, help="Limit search to a category.")
@click.pass_context
def search(ctx, query: str, category: str) -> None:
    """Search prompts by keyword using full-text search."""
    conn = _ensure_db(ctx)
    results = search_prompts(query, category or "", connection=conn)

    if not results:
        click.echo(f"No prompts matching '{query}'.")
        click.echo("Try a different search term or use 'pl list' to see all prompts.")
        return

    click.echo(f"Results for '{query}':")
    click.echo(f"{'ID':<30} {'Title'}")
    click.echo("-" * 60)
    for p in results:
        click.echo(f"{p.id:<30} {p.title}")


@cli.command()
@click.argument("prompt_id")
@click.pass_context
def get(ctx, prompt_id: str) -> None:
    """Show full prompt content by ID."""
    _ensure_db(ctx)
    prompt = get_prompt(prompt_id)

    if prompt is None:
        click.echo(f"Error: no prompt with ID '{prompt_id}'")
        return

    click.echo(f"ID:          {prompt.id}")
    click.echo(f"Title:       {prompt.title}")
    click.echo(f"Description: {prompt.description}")
    click.echo(f"Category:    {prompt.category}")
    if prompt.tags:
        click.echo(f"Tags:        {', '.join(prompt.tags)}")
    if prompt.model_hint:
        click.echo(f"Model hint:  {prompt.model_hint}")
    if prompt.variables:
        click.echo(f"\nVariables ({len(prompt.variables)}):")
        for v in prompt.variables:
            default_str = f" (default: {v.default})" if v.default else ""
            click.echo(f"  - {v.name}: {v.description}{default_str}")
    click.echo(f"\nUsage: {prompt.fetch_count} fetches, rating: {prompt.user_rating:.1f}")
    click.echo(f"\n{'-' * 60}")
    click.echo(prompt.body)
    click.echo(f"{'-' * 60}")


@cli.command()
@click.argument("prompt_id")
@click.option("--var", "-v", "cli_vars", multiple=True,
              help="Set a variable value as key=value (can be used multiple times).")
@click.pass_context
def render(ctx, prompt_id: str, cli_vars: tuple[str, ...]) -> None:
    """Render a prompt with variable substitution.

    Pass variables via ``--var key=value`` (repeatable), or leave them
    unspecified to enter values interactively.
    """
    _ensure_db(ctx)
    prompt = get_prompt(prompt_id)

    if prompt is None:
        click.echo(f"Error: no prompt with ID '{prompt_id}'")
        return

    # Parse --var key=value pairs
    values: dict[str, str] = {}
    for entry in cli_vars:
        if "=" in entry:
            key, _, val = entry.partition("=")
            values[key.strip()] = val.strip()
        else:
            click.echo(f"Warning: ignoring '--var {entry}' (expected key=value format)")

    click.echo(f"Rendering: {prompt.title}")
    click.echo(f"ID: {prompt.id}")
    click.echo(f"{'=' * 50}")

    result = render_prompt(prompt.body, prompt.variables, values=values or None)

    click.echo(f"\n{'=' * 50}")
    click.echo("RENDERED PROMPT:")
    click.echo("=" * 50)
    click.echo(result)
    click.echo("=" * 50)


@cli.command()
@click.argument("file", type=click.Path(exists=True, readable=True))
@click.pass_context
def add(ctx, file: str) -> None:
    """Add a new prompt from a YAML file."""
    conn = _ensure_db(ctx)
    source = Path(file)
    try:
        from pl.storage import _parse_yaml_frontmatter as _parse
        metadata, body = _parse(source)
        metadata["body"] = body
        prompt = Prompt(**metadata)
        storage_add(prompt, connection=conn)
        click.echo(f"Added prompt '{prompt.id}' to category '{prompt.category}'.")
    except FileExistsError as e:
        click.echo(f"Error: {e}")
    except Exception as e:
        click.echo(f"Error adding prompt: {e}")


@cli.command()
@click.pass_context
def categories(ctx) -> None:
    """List all available prompt categories with prompt counts."""
    _ensure_db(ctx)
    cats = get_categories()

    if not cats:
        click.echo("No categories found.")
        return

    click.echo("Available categories:")
    for c in cats:
        click.echo(f"  - {c['name']} ({c['count']} prompt{'s' if c['count'] != 1 else ''})")


# ── New Commands ───────────────────────────────────────────────────────────

@cli.command(name="import")
@click.option("--dir", "directory", type=click.Path(exists=True, file_okay=False),
              default=None, help="Directory containing YAML prompt files (default: prompts/).")
@click.pass_context
def import_cmd(ctx, directory: str) -> None:
    """Import prompts from YAML files into the database.

    Scans the specified directory (or the default prompts/ directory) for
    ``*.yaml`` files and imports them into the SQLite database.
    Duplicate IDs are silently skipped.
    """
    conn = _ensure_db(ctx)
    prompts_dir = Path(directory) if directory else None
    count = import_yaml(prompts_dir, connection=conn)
    click.echo(f"Imported {count} prompt(s) from YAML files.")


@cli.command(name="export")
@click.option("--dir", "directory", type=click.Path(file_okay=False),
              default="./export", help="Output directory (default: ./export).")
@click.pass_context
def export_cmd(ctx, directory: str) -> None:
    """Export all prompts from the database to YAML files.

    Creates one YAML file per prompt in ``<dir>/<category>/<id>.yaml``.
    """
    conn = _ensure_db(ctx)
    output_dir = Path(directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    count = export_yaml(output_dir, connection=conn)
    click.echo(f"Exported {count} prompt(s) to {output_dir}.")


@cli.command()
@click.pass_context
def optimize(ctx) -> None:
    """Rebuild the FTS index and VACUUM the database.

    Run this periodically to maintain search performance after many
    insertions, updates, or deletions.
    """
    conn = _ensure_db(ctx)
    with click.progressbar(length=3, label="Optimizing") as bar:
        click.echo("Rebuilding FTS index...")
        storage_optimize(connection=conn)
        bar.update(3)
    click.echo("Optimization complete. Database is now fully optimized.")


@cli.command()
@click.pass_context
def info(ctx) -> None:
    """Show database statistics."""
    conn = _ensure_db(ctx)
    stats = get_info(connection=conn)

    click.echo("Prompt Library Database Info:")
    click.echo(f"  Total prompts:  {stats['total_prompts']}")
    click.echo(f"  Total fetches:  {stats['total_fetches']}")

    size = stats["db_size_bytes"]
    if size < 1024:
        size_str = f"{size} B"
    elif size < 1024 * 1024:
        size_str = f"{size / 1024:.1f} KB"
    else:
        size_str = f"{size / (1024 * 1024):.1f} MB"
    click.echo(f"  Database size:  {size_str}")
