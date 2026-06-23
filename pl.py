#!/usr/bin/env python3
"""Prompt Library CLI — manage and use reusable prompt templates.

Usage:
    pl list                     List all prompts
    pl list --category dev      List prompts in a category
    pl search <query>           Search prompts by keyword or tag
    pl get <id>                 Show full prompt content
    pl render <id>              Render a prompt with variable substitution
    pl add <file>               Add a new prompt from a YAML file
    pl categories               List all categories
"""

from pl.commands import cli

if __name__ == "__main__":
    cli()
