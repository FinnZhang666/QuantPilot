from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.ai.service import ANALYSIS_VERSION
from app.cli.__main__ import build_parser
from app.database.models import (
    AIReviewAnalysis, CandidatePoolEntry, Opportunity, OpportunityReview,
    ResearchAttachment, ResearchInvestigation,
)
from app.research.service import ResearchService
from app.research.similarity import similarity_score

NOW = datetime(2026, 7, 29, tzinfo=timezone.utc)


def opportunity(db, symbol="SOXL", direction="LONG", score=80, regime="TRENDING"):
    row = Opportunity(
        symbol=symbol, timeframe="60m", direction=direction,
        opportunity_type="PULLBACK_RESTRENGTH",
        strategy_name="pullback_restrength", strategy_version="1.0.0",
        status="ACTIVE", score=score, confidence=85, detected_at=NOW,
        bar_time=NOW, entry_reference_price=Decimal("20"),
        market_regime=regime, feature_snapshot_json={"ema_20": "21", "atr": "1"},
        strategy_snapshot_json={"reasons": ["趋势成立"], "components": {"trend": 30}},
        decision_snapshot_json={"market_regime": regime},
        notification_status="PENDING",
    )
    db.add(row)
    db.commit()
    return row


def review(db, row, value="5"):
    result = OpportunityReview(
        opportunity_id=row.id, review_status="REVIEWED", review_time=NOW,
        holding_bars=5, holding_minutes=300, holding_days=Decimal("0.2"),
        entry_reference_price=Decimal("20"), exit_reference_price=Decimal("21"),
        last_price=Decimal("21"), mfe_percent=Decimal("8"), mae_percent=Decimal("-2"),
        return_percent=Decimal(value), max_close_return=Decimal("6"),
        min_close_return=Decimal("-1"), target_hit=True, stop_hit=False,
        expired=True, review_window="1D",
        price_path_json=[{"timestamp": NOW.isoformat(), "close": "21"}],
        statistics_json={}, reason_json={},
    )
    db.add(result)
    db.commit()
    return result


def test_workspace_created_and_idempotent(db, tmp_path):
    row = opportunity(db)
    service = ResearchService(db, tmp_path)
    first = service.ensure_workspace(row.id)
    second = service.ensure_workspace(row.id)
    assert first.id == second.id


def test_workspace_missing_opportunity(db):
    with pytest.raises(KeyError):
        ResearchService(db).ensure_workspace(999)


def test_initial_timeline(db):
    row = opportunity(db)
    service = ResearchService(db)
    workspace = service.ensure_workspace(row.id)
    names = [item.event_type for item in service.timeline(workspace.id)]
    assert "OPPORTUNITY_GENERATED" in names and "OPPORTUNITY_STATUS" in names


def test_timeline_sync_is_idempotent(db):
    row = opportunity(db)
    service = ResearchService(db)
    workspace = service.ensure_workspace(row.id)
    count = len(service.timeline(workspace.id))
    service.sync(workspace.id)
    assert len(service.timeline(workspace.id)) == count


def test_snapshot_evidence(db):
    row = opportunity(db)
    service = ResearchService(db)
    workspace = service.ensure_workspace(row.id)
    assert {"FEATURE", "STRATEGY", "DECISION", "MARKET_REGIME"} <= {
        item.evidence_type for item in service.evidence(workspace.id)
    }


def test_review_evidence_and_timeline(db):
    row = opportunity(db)
    review(db, row)
    service = ResearchService(db)
    workspace = service.ensure_workspace(row.id)
    assert "REVIEW_COMPLETED" in [item.event_type for item in service.timeline(workspace.id)]
    assert {"Return", "MFE", "MAE", "Price Path"} <= {
        item.label for item in service.evidence(workspace.id)
    }


def test_ai_review_creates_evidence_and_investigation(db):
    row = opportunity(db)
    result = review(db, row)
    analysis = AIReviewAnalysis(
        opportunity_id=row.id, opportunity_review_id=result.id,
        analysis_version=ANALYSIS_VERSION, provider="local", model="test",
        status="COMPLETED", input_snapshot_json={}, input_hash="a" * 64,
        prompt_version="v1", prompt_text_hash="b" * 64,
        summary="需要验证成交量", positive_factors_json=[], negative_factors_json=[],
        risk_factors_json=["ATR偏高"], timing_analysis_json={},
        market_regime_analysis_json={}, historical_comparison_json={},
        investigation_items_json=[{
            "title": "验证成交量", "description": "检查Volume Ratio", "priority": "HIGH",
        }],
        confidence_score=70, uncertainty_notes=[], completed_at=NOW,
    )
    db.add(analysis)
    db.commit()
    service = ResearchService(db)
    workspace = service.ensure_workspace(row.id)
    assert any(item.evidence_type == "AI_CONCLUSION" for item in service.evidence(workspace.id))
    investigation = service.investigations(workspace.id)[0]
    assert investigation.title == "验证成交量"
    assert len(investigation.evidence_ids_json) == 1


@pytest.mark.parametrize("status", ["NEW", "OPEN", "TESTING", "VERIFIED", "REJECTED", "CLOSED"])
def test_investigation_statuses(db, status):
    row = opportunity(db)
    service = ResearchService(db)
    workspace = service.ensure_workspace(row.id)
    item = ResearchInvestigation(
        workspace_id=workspace.id, title="测试", status="NEW", priority="MEDIUM",
        source_type="MANUAL", source_id="one", evidence_ids_json=[], result_json={},
    )
    db.add(item)
    db.commit()
    assert service.update_investigation(item.id, status).status == status


def test_investigation_invalid_status(db):
    row = opportunity(db)
    workspace = ResearchService(db).ensure_workspace(row.id)
    item = ResearchInvestigation(
        workspace_id=workspace.id, title="测试", status="NEW", priority="MEDIUM",
        source_type="MANUAL", source_id="one", evidence_ids_json=[], result_json={},
    )
    db.add(item)
    db.commit()
    with pytest.raises(ValueError):
        ResearchService(db).update_investigation(item.id, "AUTO_CODE")


@pytest.mark.parametrize(
    "note_type", ["OBSERVATION", "HYPOTHESIS", "VALIDATION", "EXPERIENCE", "NEXT_STEP"],
)
def test_research_note_types(db, note_type):
    row = opportunity(db)
    service = ResearchService(db)
    workspace = service.ensure_workspace(row.id)
    note = service.add_note(workspace.id, "人工研究记录", note_type)
    assert note.note_type == note_type


def test_blank_note_rejected(db):
    workspace = ResearchService(db).ensure_workspace(opportunity(db).id)
    with pytest.raises(ValueError):
        ResearchService(db).add_note(workspace.id, " ")


def test_note_appears_in_timeline(db):
    service = ResearchService(db)
    workspace = service.ensure_workspace(opportunity(db).id)
    service.add_note(workspace.id, "后续验证")
    assert "MANUAL_NOTE" in [row.event_type for row in service.timeline(workspace.id)]


@pytest.mark.parametrize("filename", ["a.png", "a.jpg", "a.jpeg", "a.csv", "a.json", "a.md"])
def test_allowed_attachments(db, tmp_path, filename):
    service = ResearchService(db, tmp_path)
    workspace = service.ensure_workspace(opportunity(db).id)
    row = service.add_attachment(workspace.id, filename, b"research")
    assert row.size_bytes == 8


def test_attachment_rejects_pdf(db, tmp_path):
    service = ResearchService(db, tmp_path)
    workspace = service.ensure_workspace(opportunity(db).id)
    with pytest.raises(ValueError):
        service.add_attachment(workspace.id, "report.pdf", b"pdf")


def test_attachment_rejects_large_file(db, tmp_path):
    service = ResearchService(db, tmp_path)
    workspace = service.ensure_workspace(opportunity(db).id)
    with pytest.raises(ValueError):
        service.add_attachment(workspace.id, "large.csv", b"x" * (10 * 1024 * 1024 + 1))


def test_attachment_hash_and_safe_name(db, tmp_path):
    service = ResearchService(db, tmp_path)
    workspace = service.ensure_workspace(opportunity(db).id)
    row = service.add_attachment(workspace.id, "../../my chart.png", b"image")
    assert len(row.sha256) == 64 and ".." not in row.stored_name


def test_similarity_prefers_matching_case(db):
    current = opportunity(db, "SOXL", "LONG", 80)
    matching = opportunity(db, "TQQQ", "LONG", 82)
    different = opportunity(db, "SOXS", "SHORT", 20, "RISK_OFF")
    service = ResearchService(db)
    workspace = service.ensure_workspace(current.id)
    rows = service.similarity(workspace.id)
    assert rows[0]["opportunity_id"] == matching.id
    assert rows[-1]["opportunity_id"] == different.id


def test_similarity_excludes_self_and_limits(db):
    current = opportunity(db, "SOXL")
    opportunity(db, "TQQQ")
    opportunity(db, "APP")
    service = ResearchService(db)
    workspace = service.ensure_workspace(current.id)
    rows = service.similarity(workspace.id, 1)
    assert len(rows) == 1 and rows[0]["opportunity_id"] != current.id


def test_similarity_pure_function_bounds():
    left = SimpleNamespace(direction="LONG", strategy_name="s", timeframe="1d",
                           market_regime="UP", score=100, confidence=100)
    right = SimpleNamespace(direction="LONG", strategy_name="s", timeframe="1d",
                            market_regime="UP", score=100, confidence=100)
    assert similarity_score(left, right) == 95.0


def test_list_filter_count_and_detail(db):
    service = ResearchService(db)
    first = service.ensure_workspace(opportunity(db, "SOXL").id)
    service.ensure_workspace(opportunity(db, "APP").id)
    assert service.count("SOXL") == 1
    assert service.list("APP")[0].symbol == "APP"
    assert service.detail(first.id)["opportunity"].symbol == "SOXL"


def test_sync_all_creates_every_workspace(db):
    opportunity(db, "SOXL")
    opportunity(db, "APP")
    service = ResearchService(db)
    assert len(service.sync_all()) == 2
    assert service.count() == 2


@pytest.mark.parametrize(
    "arguments",
    [
        ["research", "show", "--symbol", "SOXL"],
        ["research", "timeline", "--id", "1"],
        ["research", "note", "--id", "1", "--content", "观察"],
        ["research", "similarity", "--id", "1"],
    ],
)
def test_research_cli_parser(arguments):
    args = build_parser().parse_args(arguments)
    assert args.group == "research"
