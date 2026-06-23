"""Variable substitution engine for prompt templates.

Parses ``{{variable}}`` patterns from prompt body text and interactively
substitutes values, using declared defaults when available.
Supports pre-supplied values via the ``values`` parameter for CLI use.
"""

import re
from typing import Dict, List, Optional

from pl.models import Variable

VARIABLE_PATTERN = re.compile(r"\{\{(.+?)\}\}")


def extract_variables(body: str) -> List[str]:
    """Extract all ``{{variable}}`` names from a template body.

    Returns:
        A list of variable name strings in the order they appear.
    """
    return VARIABLE_PATTERN.findall(body)


def render_prompt(
    body: str,
    variables: List[Variable],
    values: Optional[Dict[str, str]] = None,
) -> str:
    """Render a prompt by substituting template variables with user-provided values.

    Uses pre-supplied ``values`` first (from ``--var`` CLI flags), then falls
    back to declared defaults, and finally prompts interactively for any
    remaining variables not declared in metadata.

    Args:
        body: The prompt template body containing ``{{variable}}`` placeholders.
        variables: List of declared Variable models with name/description/default.
        values: Optional dict of pre-supplied variable values (from CLI ``--var``).

    Returns:
        The fully rendered body with all variables substituted.
    """
    declared = {v.name: v for v in variables}
    preset = dict(values) if values else {}
    used_vars = extract_variables(body)

    resolved: dict[str, str] = {}

    for var_name in used_vars:
        # Priority: pre-supplied > declared default > interactive prompt
        if var_name in preset:
            resolved[var_name] = preset[var_name]
        elif var_name in declared:
            var = declared[var_name]
            prompt_text = (
                f"Enter value for '{var_name}'"
                f" ({var.description or 'no description'}): "
            )
            user_input = input(prompt_text).strip()
            resolved[var_name] = user_input if user_input else (var.default or "")
        else:
            print(
                f"Warning: Variable '{{{var_name}}}' is not declared in prompt metadata."
            )
            resolved[var_name] = input(f"Enter value for '{var_name}': ").strip()

    result = body
    for var_name, value in resolved.items():
        result = result.replace("{{" + var_name + "}}", value)

    return result
