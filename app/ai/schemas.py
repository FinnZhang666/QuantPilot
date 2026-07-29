from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OpportunityContext(BaseModel):
    symbol: str
    direction: str
    strategy: str
    timeframe: str
    entry_price: str
    detected_at: str
    notified_at: Optional[str] = None
    confidence: Optional[int] = None
    score: int
    target_price: Optional[str] = None
    stop_price: Optional[str] = None
    expiry: Optional[str] = None


class ReviewContext(BaseModel):
    final_status: str
    reviewed_at: str
    review_window: str
    return_percent: str
    mfe_percent: str
    mae_percent: str
    holding_duration: Dict[str, Any]
    target_hit: Optional[bool] = None
    stop_hit: Optional[bool] = None
    price_path_summary: Dict[str, Any]
    window_returns: Dict[str, Optional[str]]
    data_quality: str
    failure_reason: Optional[str] = None


class MarketRegimeContext(BaseModel):
    regime: str
    confidence: int
    trend: int
    volatility: int
    breadth: Optional[int] = None
    risk_state: int
    generated_at: str


class CandidatePoolContext(BaseModel):
    pool_score: int
    rank: Optional[int] = None
    direction: str
    reasons: List[str]
    rejected_reasons: List[str]
    run_id: Optional[int] = None


class StrategyContext(BaseModel):
    name: str
    version: str
    opportunity_type: str
    decision_snapshot: Dict[str, Any]


class HistoricalGroup(BaseModel):
    sample_size: int = 0
    success_rate: str = "0"
    average_return: str = "0"
    average_mfe: str = "0"
    average_mae: str = "0"
    max_return: str = "0"
    max_drawdown: str = "0"
    coverage_rate: str = "0"


class HistoricalStatisticsContext(BaseModel):
    same_strategy: HistoricalGroup
    same_symbol: HistoricalGroup
    same_timeframe: HistoricalGroup
    same_direction: HistoricalGroup
    same_market_regime: HistoricalGroup
    global_statistics: HistoricalGroup


class AnalysisMetadata(BaseModel):
    analysis_version: str
    prompt_version: str
    generated_at: str
    facts_only: bool = True


class AIReviewRequest(BaseModel):
    opportunity: OpportunityContext
    review: ReviewContext
    market_regime: Optional[MarketRegimeContext] = None
    candidate_pool: Optional[CandidatePoolContext] = None
    feature_snapshot: Optional[Dict[str, Any]] = None
    strategy: StrategyContext
    historical_statistics: HistoricalStatisticsContext
    metadata: AnalysisMetadata


class TimingAnalysis(BaseModel):
    entry_timing: str
    exit_timing: str
    mfe_mae_interpretation: str
    target_stop_interpretation: str


class MarketRegimeAnalysis(BaseModel):
    alignment: str
    evidence: List[str]
    uncertainty: str


class HistoricalComparison(BaseModel):
    comparison_summary: str
    sample_size_warning: str
    differences: List[str]


class InvestigationItem(BaseModel):
    title: str
    category: str
    evidence: str
    priority: str = Field(pattern="^(LOW|MEDIUM|HIGH)$")


class AIReviewResponse(BaseModel):
    summary: str
    outcome_classification: str = Field(
        pattern="^(STRONG_SUCCESS|MODERATE_SUCCESS|NEUTRAL|MODERATE_FAILURE|STRONG_FAILURE|INCONCLUSIVE)$"
    )
    facts: List[str]
    positive_factors: List[str]
    negative_factors: List[str]
    risk_factors: List[str]
    timing_analysis: TimingAnalysis
    market_regime_analysis: MarketRegimeAnalysis
    historical_comparison: HistoricalComparison
    investigation_items: List[InvestigationItem]
    confidence_score: int = Field(ge=0, le=100)
    uncertainty_notes: List[str]


class ProviderResult(BaseModel):
    response: AIReviewResponse
    raw_response: Optional[Dict[str, Any]] = None
    token_input: Optional[int] = None
    token_output: Optional[int] = None
    estimated_cost: Optional[str] = None
