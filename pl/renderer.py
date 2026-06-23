"""Variable substitution engine for prompt templates.

Parses ``{{variable}}`` patterns from prompt body text and interactively
substitutes values, using declared defaults when available.
"""

import re
from typing import List

from pl.models import Variable

VARIABLE_PATTERN = re.compile(r"\{\{(.+?)\}\}")


def extract_variables(body: str) -> List[str]:
    """Extract all ``{{variable}}`` names from a template body.

    Returns:
        A list of variable name strings in the order they appear.
    """
    return VARIABLE_PATTERN.findall(body)


def render_prompt(body: str, variables: List[Variable]) -> str:
    """Render a prompt by substituting template variables with user-provided values.

    For each variable found in the body:
      - If declared in metadata with a default, use the default if the user
        provides no input.
      - If declared without a default, prompt the user for a value.
      - If NOT declared in metadata, warn and prompt the user anyway.

    Args:
        body: The prompt template body containing ``{{variable}}`` placeholders.
        variables: List of declared Variable models with name/description/default.

    Returns:
        The fully rendered body with all variables substituted.
    """
    declared = {v.name: v for v in variables}
    used_vars = extract_variables(body)

    values: dict[str, str] = {}

    for var_name in used_vars:
        if var_name in declared:
            var = declared[var_name]
            prompt_text = (
                f"Enter value for '{var_name}'"
                f" ({var.description or 'no description'}): "
            )
            user_input = input(prompt_text).strip()
            values[var_name] = user_input if user_input else (var.default or "")
        else:
            print(
                f"Warning: Variable '{{{var_name}}}' is not declared in prompt metadata."
            )
            values[var_name] = input(f"Enter value for '{var_name}': ").strip()

    result = body
    for var_name, value in values.items():
        result = result.replace("{{" + var_name + "}}", value)

    return result
