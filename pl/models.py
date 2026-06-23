from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class Variable(BaseModel):
    """A template variable with metadata for interactive substitution."""

    name: str
    description: str = ""
    default: Optional[str] = None


class Prompt(BaseModel):
    """A prompt template with full metadata, body content, and usage tracking."""

    id: str = Field(
        ...,
        pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$",
        description="Unique kebab-case identifier",
    )
    title: str
    description: str = ""
    category: str
    tags: list[str] = Field(default_factory=list)
    model_hint: str = ""
    variables: list[Variable] = Field(default_factory=list)
    version: str = "1.0"
    created: Optional[date] = None
    updated: Optional[date] = None
    body: str = ""
    fetch_count: int = 0
    user_rating: float = 0.0
