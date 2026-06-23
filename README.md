# Prompt Library

> A local library to store, organize, and manage reusable AI prompt templates.

`pl` is a command-line prompt manager that lets you build a personal collection of prompt templates — organized by category, searchable by keyword or tag, and renderable with variable substitution. Powered by **SQLite with FTS5 full-text search** for fast, deterministic local storage.

---

## Features

- **SQLite-backed storage** — prompts live in a local SQLite database, not loose files. YAML files are used only for import/export.
- **FTS5 full-text search** — BM25-ranked search with Porter stemming, prefix wildcards, and usage-based scoring.
- **Variable substitution** — define `{{variables}}` in templates and render them via `--var` flags or interactively.
- **Model hints** — tag prompts with the models they work best with.
- **Import / Export** — bulk-import YAML prompt files into SQLite, and export back out for sharing.
- **Ledger audit trail** — optional append-only transaction log enabled via `PROMPT_LIBRARY_LEDGER=1`.
- **Simple CLI** — one command (`pl`) for everything.

---

## Setup

### Requirements

- Python 3.10+
- pip

### Install

```bash
git clone https://github.com/hey1me/Prompt-Library.git
cd Prompt-Library
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

That's it. The `pl` command is now available globally.

---

## Usage

```bash
# List all prompts
pl list

# Filter by category
pl list --category development

# Search by keyword or tag
pl search "code review"

# Show a prompt's full content
pl get code-review

# Render a prompt (interactive or with --var flags)
pl render code-review
pl render code-review --var language=python --var code_snippet="..."

# Add a single prompt from a YAML file
pl add my-prompt.yaml

# Bulk-import all YAML prompts from a directory
pl import --dir prompts/

# Export database to YAML files
pl export --dir ./export

# List all categories with prompt counts
pl categories

# Show database statistics
pl info

# Optimize the database (rebuild FTS index + VACUUM)
pl optimize
```

---

## Prompt Format

Prompts are defined as YAML files with frontmatter metadata and a body template. These serve as the **import/export format**; actual storage is in SQLite.

```yaml
id: my-prompt
title: My Prompt Title
description: What this prompt does
category: development
tags: [tag1, tag2]
model_hint: claude, gpt4
variables:
  - name: variable_name
    description: What this variable represents
    default: optional_default
version: "1.0"
created: 2026-01-01
updated: 2026-01-01
---
Your prompt template goes here.

Use {{variable_name}} for substitution.
```

The `---` separator divides frontmatter (YAML metadata) from the prompt body.

---

## Project Structure

```
Prompt-Library/
├── pl/                  # CLI source code
│   ├── commands.py      # Click command definitions
│   ├── database.py      # SQLite connection & schema (FTS5)
│   ├── ledger.py        # Optional audit trail
│   ├── migrations.py    # Schema migrations
│   ├── models.py        # Pydantic prompt data models
│   ├── renderer.py      # Variable substitution engine
│   ├── search.py        # FTS5 search with BM25 + usage scoring
│   └── storage.py       # SQLite CRUD, YAML import/export
├── prompts/             # Example prompt library (YAML source files)
│   ├── analysis/
│   ├── development/
│   └── writing/
├── tests/               # Test suite (pytest)
│   ├── conftest.py
│   ├── fixtures/prompts/
│   └── test_*.py
├── pl.py                # Entry point
└── pyproject.toml
```

---

## Adding Your Own Prompts

### Option 1: Add a single YAML file

```bash
pl add path/to/my-prompt.yaml
```

The prompt is parsed, validated, and inserted into the SQLite database.

### Option 2: Bulk-import a directory

```bash
pl import --dir prompts/
```

Scans the directory recursively for `*.yaml` files, parses frontmatter, and inserts each one. **Duplicate IDs are silently skipped**, making imports idempotent.

### Option 3: Manual database insert

```bash
pl import --dir path/to/my-prompts/
```

---

## Search

The search engine uses **FTS5 BM25 ranking** combined with a usage-based weight:

```
Final Rank = BM25_text_score + (log10(fetch_count + 1) * user_rating)
```

The fallback chain ensures you always get results:

1. **FTS5 AND query** — exact match on all terms with BM25 ranking
2. **Prefix wildcard OR** — `term*` on each term when AND returns nothing
3. **LIKE scan** — last resort scan on title and description columns

Usage scoring means frequently fetched, highly-rated prompts rank higher — the system gets smarter the more you use it.

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `PROMPT_LIBRARY_DB` | Path to the SQLite database | `~/.local/share/prompt-library/library.db` |
| `PROMPT_LIBRARY_LEDGER` | Enable audit trail (`1` to enable) | disabled |
| `XDG_DATA_HOME` | Base directory for XDG data (DB location) | `~/.local/share` |

---

## Database

The database is stored at `~/.local/share/prompt-library/library.db` (XDG-compliant). It uses:

- **WAL journal mode** for concurrent reads
- **FTS5 virtual table** for full-text search
- **Triggers** to keep the FTS index in sync on INSERT/UPDATE/DELETE
- **Porter stemmer** for English word stemming (e.g., "reviewing" → "review")

Run `pl optimize` periodically to rebuild the FTS index and reclaim space.

---

## Contribution

> [!NOTE]
> If you are interested in adding features, feel free to open a Pull Request.

---

## License

MIT
