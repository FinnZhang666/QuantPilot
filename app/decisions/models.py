from typing import Any, Dict

from pydantic import BaseModel, Field


class Decision(BaseModel):
    approved: bool
    reason: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
