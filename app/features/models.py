from typing import Any, Dict

from pydantic import BaseModel, Field


class FeatureSet(BaseModel):
    symbol: str
    values: Dict[str, Any] = Field(default_factory=dict)
