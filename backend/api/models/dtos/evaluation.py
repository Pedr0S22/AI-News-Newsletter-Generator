import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


# ==============================================================================
# Strict Structured JSON Schemas Returned by ADK Agents
# ==============================================================================


class TopicAgentOutput(BaseModel):
    is_ai_topic: bool = Field(..., description="True if the article is genuinely about Artificial Intelligence.")
    primary_theme: str = Field(..., description="Short editorial category tag (e.g. LLMs & Reasoning, AI Agents, AI Safety & Policy).")
    reason: str = Field(..., description="Concise plain-English explanation of why this is or is not an AI story.")


class HypeAgentOutput(BaseModel):
    hype_score: float = Field(..., ge=1.0, le=10.0, description="Sensationalism / speculation score from 1 (purely grounded) to 10 (extreme hype).")
    reason: str = Field(..., description="Plain-English justification citing concrete signals of groundedness or hype.")


class FactualityAgentOutput(BaseModel):
    factuality_score: float = Field(..., ge=1.0, le=10.0, description="Factual reliability score from 1 (unsupported) to 10 (strongly verified).")
    reason: str = Field(..., description="Plain-English justification explaining what was verified or unverified across sources.")


class DeduplicationAgentOutput(BaseModel):
    is_duplicate: bool = Field(..., description="True if the article reports the exact same event/release as an existing article.")
    duplicate_of_article_id: Optional[str] = Field(None, description="ID of the earlier/primary article if duplicate, else null.")
    reason: str = Field(..., description="Plain-English explanation of the duplication decision.")


# ==============================================================================
# API Response DTOs
# ==============================================================================


class VerificationSourceDTO(BaseModel):
    title: str
    url: str
    snippet: str = ""
    origin: str = "web"  # "web" or "database"


class EvaluatedArticleDTO(BaseModel):
    article_id: uuid.UUID
    source: str
    canonical_url: str
    original_url: Optional[str] = None
    title: str
    summary: Optional[str] = None
    author: Optional[str] = None
    published_at: datetime

    # Evaluation fields
    is_ai_topic: bool
    primary_theme: Optional[str] = None
    topic_reason: Optional[str] = None

    hype_score: Optional[float] = None
    groundedness_score: Optional[float] = None
    hype_reason: Optional[str] = None

    factuality_score: Optional[float] = None
    factuality_reason: Optional[str] = None
    verification_sources: list[VerificationSourceDTO] = Field(default_factory=list)

    is_duplicate: bool = False
    duplicate_of_article_id: Optional[uuid.UUID] = None
    dedup_reason: Optional[str] = None

    weighted_subscore: float = 0.0
    reputation_multiplier: float = 1.0
    final_ranking_score: float = 0.0
    status: str = "ranked"
    recommended_rank: Optional[int] = None


class RankingsResponse(BaseModel):
    top_n: int
    recommended: list[EvaluatedArticleDTO]
    candidate_pool: list[EvaluatedArticleDTO]
    eliminated: list[EvaluatedArticleDTO]
    unevaluated_count: int = 0


class EvaluationRunResponse(BaseModel):
    status: str
    evaluated_count: int
    ranked_count: int
    eliminated_topic_count: int
    eliminated_duplicate_count: int
    failed_count: int = 0


class SourceReputationDTO(BaseModel):
    source_name: str
    reputation_score: float
    accepted_count: int
    rejected_count: int
    edited_count: int
    promoted_count: int
    total_evaluated: int
    history: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnalyticsResponse(BaseModel):
    reputations: list[SourceReputationDTO]
    total_articles: int
    total_evaluated: int
    total_eliminated: int
    editions_drafted: int
    editions_sent: int
    active_subscribers: int
    avg_top_n_retention_rate: Optional[float] = None
    unedited_approval_rate: Optional[float] = None
    avg_edit_ratio: Optional[float] = None
