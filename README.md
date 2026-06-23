# Prompt Library

> A local library to store, organize, and manage reusable AI prompt templates.

`pl` is a command-line prompt manager that lets you build a personal collection of prompt templates — organized by category, searchable by keyword or tag, and renderable with variable substitution. Think of it as a local, version-controlled prompt store you fully own.

---

## Features

- **Organized storage** — prompts live as YAML files grouped by category
- **Variable substitution** — define `{{variables}}` in templates and render them on the fly
- **Search & filter** — find prompts by keyword, tag, or category
- **Model hints** — tag prompts with the models they work best with
- **Simple CLI** — one command (`pl`) for everything

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

# Render a prompt with variable values
pl render code-review --var language=python --var code_snippet="..."

# Add a new prompt from a YAML file
pl add my-prompt.yaml

# List all categories
pl categories
```

---

## Prompt Format

Prompts are YAML files stored under `prompts/<category>/`. Here's the structure:

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

---

## Project Structure

```
Prompt-Library/
├── pl/                  # CLI source code
│   ├── commands.py      # CLI entry points
│   ├── models.py        # Prompt data models
│   ├── renderer.py      # Variable substitution engine
│   ├── search.py        # Search and filter logic
│   └── storage.py       # YAML file I/O
├── prompts/             # Your prompt library
│   ├── analysis/
│   ├── development/
│   └── writing/
├── pl.py                # Entry point
└── pyproject.toml
```

---

## Adding Your Own Prompts

1. Create a YAML file following the format above
2. Place it in `prompts/<your-category>/` (create the folder if needed)
3. Run `pl list` to confirm it's picked up

Or use the CLI directly:

```bash
pl add path/to/my-prompt.yaml
```

---

## Contribution

> [!NOTE]
> If you are interested in adding features, feel free to open "Pull Request".

---

## License

MIT
