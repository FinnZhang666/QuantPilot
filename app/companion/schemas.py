from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


CONTEXT_SCHEMA_VERSION = "companion-context-v1"
RESPONSE_SCHEMA_VERSION = "companion-response-v1"
DISCLAIMER_ZH = "以上内容仅解释系统已有数据，不构成新的交易信号或投资建议。"


class CompanionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = CONTEXT_SCHEMA_VERSION
    context_type: str
    generated_at: datetime
    product: str = "Trade Companion"
    trade_plan: Optional[Dict[str, Any]] = None
    user_position: Optional[Dict[str, Any]] = None
    review: Optional[Dict[str, Any]] = None
    statistics: Dict[str, Any]
    missing_fields: List[str] = Field(default_factory=list)
    source_references: Dict[str, Any]


class CompanionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = RESPONSE_SCHEMA_VERSION
    summary: str = Field(min_length=1, max_length=2000)
    plan_interpretation: str = Field(min_length=1, max_length=4000)
    risk_notes: List[str] = Field(max_length=20)
    positive_factors: List[str] = Field(max_length=20)
    caution_factors: List[str] = Field(max_length=20)
    missing_data_notes: List[str] = Field(max_length=30)
    lifecycle_guidance: str = Field(min_length=1, max_length=2000)
    review_interpretation: Optional[str] = Field(default=None, max_length=4000)
    disclaimer: str = DISCLAIMER_ZH
    provider_metadata: Dict[str, Any] = Field(default_factory=dict)


class ProviderResult(BaseModel):
    response: Any
    request_id: Optional[str] = None
    latency_ms: int = 0
    provider: str
    model: str
    token_input: Optional[int] = None
    token_output: Optional[int] = None
