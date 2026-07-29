from app.ai.schemas import AIReviewRequest, AIReviewResponse, ProviderResult


class MockAIProvider:
    name = "mock"
    model = "mock-review-v1"

    def analyze_review(self, request: AIReviewRequest) -> ProviderResult:
        value = float(request.review.return_percent)
        classification = "MODERATE_SUCCESS" if value > 0 else (
            "MODERATE_FAILURE" if value < 0 else "NEUTRAL"
        )
        response = AIReviewResponse.model_validate({
            "summary": "TEST / MOCK OUTPUT：固定结构化复盘结果。",
            "outcome_classification": classification,
            "facts": ["最终收益为%s%%。" % request.review.return_percent],
            "positive_factors": ["Mock正向因素"],
            "negative_factors": ["Mock负向因素"],
            "risk_factors": ["Mock结果仅供自动化测试"],
            "timing_analysis": {
                "entry_timing": "Mock入场时点分析", "exit_timing": "Mock退出时点分析",
                "mfe_mae_interpretation": "Mock MFE/MAE分析",
                "target_stop_interpretation": "Mock目标止损分析",
            },
            "market_regime_analysis": {
                "alignment": "UNKNOWN", "evidence": [],
                "uncertainty": "Mock不形成真实市场结论",
            },
            "historical_comparison": {
                "comparison_summary": "Mock历史比较", "sample_size_warning": "Mock样本",
                "differences": [],
            },
            "investigation_items": [{
                "title": "Mock调查项", "category": "TEST",
                "evidence": "仅用于测试", "priority": "LOW",
            }],
            "confidence_score": 50,
            "uncertainty_notes": ["这是Mock输出，不得计入真实AI统计。"],
        })
        return ProviderResult(response=response, raw_response=response.model_dump())
