from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.events import publish
from app.modules.crm.models import Lead, ScoreFact
from app.modules.identity.models import User

MODEL_VERSION = "rule-v1"


SOURCE_WEIGHTS = {
    "meta_lead_ads": 18,
    "whatsapp": 14,
    "facebook": 8,
    "instagram": 8,
    "referral": 12,
    "event": 10,
    "website": 8,
    "manual": 2,
}

STATUS_WEIGHTS = {
    "new": 0,
    "contacted": 2,
    "qualified": 5,
    "proposal": 5,
    "negotiation": 5,
    "won": 10,
    "lost": -20,
}


def _grade(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def _trend(score: int, previous: Optional[int]) -> str:
    if previous is None:
        return "new"
    if score > previous:
        return "up"
    if score < previous:
        return "down"
    return "flat"


def _recency_weight(value: Optional[datetime]) -> int:
    if value is None:
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - value).total_seconds()
    if age <= 7 * 86400:
        return 8
    if age <= 30 * 86400:
        return 4
    return 0


def calculate_lead_score(lead: Lead, previous_score: Optional[int] = None) -> dict[str, Any]:
    features: dict[str, int] = {"base": 15}
    features["source"] = SOURCE_WEIGHTS.get((lead.source or "").lower(), 2)
    features["email"] = 10 if lead.email else 0
    features["phone"] = 10 if lead.phone else 0
    features["company_name"] = 5 if lead.company_name else 0

    estimated = lead.estimated_value or Decimal("0")
    if estimated >= Decimal("100000"):
        features["estimated_value"] = 15
    elif estimated >= Decimal("50000"):
        features["estimated_value"] = 10
    elif estimated >= Decimal("10000"):
        features["estimated_value"] = 5
    else:
        features["estimated_value"] = 0

    features["whatsapp_opt_in"] = 6 if lead.whatsapp_opt_in else 0
    features["engagement"] = min(15, (lead.engagement_count or 0) * 2)
    features["recency"] = _recency_weight(lead.last_activity_at)
    features["status"] = STATUS_WEIGHTS.get((lead.status or "").lower(), 0)

    score = max(0, min(100, sum(features.values())))
    ranked = sorted(features.items(), key=lambda item: (-abs(item[1]), item[0]))
    top_features = [
        {"name": name, "points": points}
        for name, points in ranked
        if points and name != "base"
    ][:3]
    return {
        "score": score,
        "grade": _grade(score),
        "trend": _trend(score, previous_score),
        "model_version": MODEL_VERSION,
        "features": {**features, "top_features": top_features},
    }


async def rescore_lead(
    db: AsyncSession,
    lead: Lead,
    *,
    user: Optional[User] = None,
    source_event_id: Optional[str] = None,
    commit: bool = True,
) -> ScoreFact:
    previous = await db.scalar(
        select(ScoreFact)
        .where(
            ScoreFact.tenant_id == lead.tenant_id,
            ScoreFact.lead_id == lead.id,
        )
        .order_by(ScoreFact.computed_at.desc(), ScoreFact.created_at.desc())
        .limit(1)
    )
    result = calculate_lead_score(lead, previous.score if previous else None)
    now = datetime.now(timezone.utc)
    event_id = source_event_id or f"lead:{lead.id}:manual:{uuid4().hex}"

    lead.score = result["score"]
    lead.score_model_version = result["model_version"]
    lead.score_updated_at = now
    lead.score_grade = result["grade"]
    lead.score_trend = result["trend"]
    lead.score_features = result["features"]

    fact = ScoreFact(
        tenant_id=lead.tenant_id,
        created_by_id=user.id if user else None,
        lead_id=lead.id,
        model_version=result["model_version"],
        score=result["score"],
        grade=result["grade"],
        trend=result["trend"],
        features=result["features"],
        source_event_id=event_id,
        computed_at=now,
    )
    db.add(fact)
    await db.flush()
    await record_audit(
        db,
        user=user,
        action="score",
        module="crm",
        entity="Lead",
        entity_id=lead.id,
        changes={
            "score": result["score"],
            "grade": result["grade"],
            "model_version": result["model_version"],
        },
    )
    if commit:
        await db.commit()
        await db.refresh(lead)
        await db.refresh(fact)
        await publish(
            "lead.scored",
            {
                "tenant_id": str(lead.tenant_id) if lead.tenant_id else None,
                "lead_id": str(lead.id),
                "score": result["score"],
                "grade": result["grade"],
                "model_version": result["model_version"],
                "source_event_id": event_id,
            },
        )
    return fact
