from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_permissions
from app.db.session import get_db
from app.modules.ai.schemas import AssistantAnswer, AssistantQuestion, InsightResponse
from app.modules.ai.service import answer_question, insights
from app.modules.identity.models import User

router = APIRouter(prefix="/ai", tags=["AI Assistant"])


@router.post("/ask", response_model=AssistantAnswer)
async def ask_assistant(
    payload: AssistantQuestion,
    user: User = Depends(require_permissions("ai.assistant.use")),
    db: AsyncSession = Depends(get_db),
):
    return await answer_question(db, user, payload.question)


@router.get("/insights", response_model=InsightResponse)
async def list_insights(
    user: User = Depends(require_permissions("ai.assistant.use")),
    db: AsyncSession = Depends(get_db),
):
    return {"insights": await insights(db, user)}
