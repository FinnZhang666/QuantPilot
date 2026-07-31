from app.companion.schemas import CompanionResponse, ProviderResult


class MockCompanionProvider:
    name = "mock"
    model = "mock-companion-v1"

    def generate(self, context, template):
        plan = context.trade_plan or {
            "symbol": "SYSTEM_STATISTICS", "direction": "N/A", "lifecycle_stage": "STATISTICS",
        }
        missing = ["%s：暂无（策略未提供）" % name for name in context.missing_fields]
        response = CompanionResponse(
            summary="TEST / MOCK OUTPUT：对%s既有数据的确定性解释。" % plan.get("symbol", "未知标的"),
            plan_interpretation=(
                "当前仅解释既有基础胜负统计，不推导收益率或未来胜率。"
                if context.context_type == "STATISTICS" else
                "系统方向为%s，当前生命周期为%s；本解释不改变计划。" % (
                    plan.get("direction"), plan.get("lifecycle_stage"),
                )
            ),
            risk_notes=["Mock结果仅用于本地架构与Schema测试。"],
            positive_factors=["系统已有结构化Trade Plan。"],
            caution_factors=["任何参与决定仍需用户独立判断。"],
            missing_data_notes=missing,
            lifecycle_guidance="仅解释当前%s阶段，不推进生命周期。" % plan.get("lifecycle_stage"),
            review_interpretation=(
                "客观Review结果为%s，MFE/MAE保持原值。" % context.review.get("result")
                if context.review else None
            ),
            provider_metadata={"is_mock": True, "template_id": template.template_id},
        )
        return ProviderResult(
            response=response.model_dump(), provider=self.name, model=self.model,
            request_id="mock-deterministic", latency_ms=0,
        )
