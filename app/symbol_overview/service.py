from app.companion.service import CompanionService
from app.market_snapshot.models import snapshot_dict
from app.market_snapshot.service import MarketSnapshotService
from app.symbol_overview.models import SymbolOverview
from app.symbol_overview.repository import SymbolOverviewRepository


class SymbolOverviewService:
    def __init__(self, db):
        self.db = db
        self.snapshots = MarketSnapshotService(db)
        self.repository = SymbolOverviewRepository(db)

    def get(self, symbol, market="US"):
        snapshot = self.snapshots.get_snapshot(symbol, market)
        plan = self.repository.latest_plan(snapshot.symbol, snapshot.market)
        holding = self.repository.latest_holding(snapshot.symbol, snapshot.market)
        review = self.repository.latest_review(plan.id if plan else None, holding)
        analyses = self.repository.analyses(
            plan.id if plan else None, holding, review.id if review else None,
        )
        plan_value, holding_value = self._plan(plan), self._holding(holding)
        review_value = self._review(review)
        analysis_values = [self._analysis(row) for row in analyses]
        related = self._related(snapshot.symbol, plan_value, holding_value, review_value,
                                analysis_values[0] if analysis_values else None)
        return SymbolOverview(
            snapshot.symbol, snapshot.market, snapshot, plan_value, holding_value,
            review_value, analysis_values[0] if analysis_values else None,
            analysis_values, related,
        )

    def ai_entry(self, symbol, market="US", **options):
        overview = self.get(symbol, market)
        service = CompanionService(self.db)
        if overview.review:
            result = service.generate_review_analysis(overview.review["id"], **options)
            source = "TRADE_REVIEW"
        elif overview.holding and overview.holding.get("user_position_id"):
            result = service.generate_position_analysis(overview.holding["user_position_id"], **options)
            source = "USER_POSITION"
        elif overview.trade_plan:
            result = service.generate_trade_plan_analysis(overview.trade_plan["plan_id"], **options)
            source = "TRADE_PLAN"
        else:
            raise ValueError("该标的暂无可用于AI解释的Trade Plan、Holding关联或Review。")
        return {"generated_from": source, **result}

    @staticmethod
    def serialize(value):
        return {"symbol": value.symbol, "market": value.market,
                "snapshot": snapshot_dict(value.snapshot), "trade_plan": value.trade_plan,
                "holding": value.holding, "review": value.review,
                "ai_analysis": value.ai_analysis, "ai_history": value.ai_history,
                "related_objects": value.related_objects}

    @staticmethod
    def _plan(row):
        if row is None: return None
        return {"id": row.id, "plan_id": row.plan_id, "strategy_name": row.strategy_name,
                "strategy_version": row.strategy_version, "timeframe": row.timeframe,
                "direction": row.direction, "lifecycle_stage": row.lifecycle_stage,
                "status": row.plan_status, "score": row.score, "updated_at": row.updated_at}

    @staticmethod
    def _holding(row):
        if row is None: return None
        return {"id": row.id, "portfolio_id": row.portfolio_id, "symbol": row.symbol,
                "status": row.status, "direction": row.direction,
                "quantity": str(row.quantity), "average_cost": str(row.average_cost),
                "trade_plan_id": row.trade_plan_id, "user_position_id": row.user_position_id,
                "updated_at": row.updated_at}

    @staticmethod
    def _review(row):
        if row is None: return None
        return {"id": row.id, "review_type": row.review_type, "result": row.result,
                "mfe": str(row.mfe), "mae": str(row.mae),
                "holding_minutes": row.holding_minutes, "review_time": row.review_time}

    @staticmethod
    def _analysis(row):
        return {"id": row.id, "context_type": row.context_type, "status": row.status,
                "summary": row.summary, "language": row.language, "provider": row.provider,
                "model": row.model, "created_at": row.created_at}

    @staticmethod
    def _related(symbol, plan, holding, review, analysis):
        values = {
            "snapshot": (True, "/dashboard/market-snapshots/%s" % symbol),
            "trade_plan": (bool(plan), "/dashboard/trade-plans/%s" % plan["plan_id"] if plan else None),
            "holding": (bool(holding), "/dashboard/holdings/%s" % holding["id"] if holding else None),
            "review": (bool(review), "/dashboard/trade-reviews/%s" % review["id"] if review else None),
            "ai": (bool(analysis), "/dashboard/companion/%s" % analysis["id"] if analysis else None),
        }
        result = {name: {"available": available, "url": url}
                  for name, (available, url) in values.items()}
        result["ai"]["can_generate"] = bool(
            plan or (holding and holding.get("user_position_id")) or review
        )
        result["ai"]["action_url"] = "/internal/symbols/%s/ai-analysis" % symbol
        return result
