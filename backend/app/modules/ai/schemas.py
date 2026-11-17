from typing import Any

from pydantic import Field

from app.core.schemas import ORMModel


class AssistantQuestion(ORMModel):
    question: str = Field(min_length=2, max_length=500)


class AssistantAnswer(ORMModel):
    question: str
    intent: str
    answer: str
    data: dict[str, Any]
    suggestions: list[str]


class Insight(ORMModel):
    severity: str
    title: str
    detail: str
    metric: str
    action: str


class InsightResponse(ORMModel):
    insights: list[Insight]
