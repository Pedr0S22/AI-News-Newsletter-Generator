import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


# ==============================================================================
# Structured JSON Newsletter Contract (Intro, Blurbs, Outro — Zero Internal Scores)
# ==============================================================================


class NewsletterBlurbDTO(BaseModel):
    article_id: str
    rank_order: int = Field(..., ge=1)
    theme: str = "AI News"
    headline: str
    body: str
    source_name: str
    source_url: str


class NewsletterStructuredContent(BaseModel):
    edition_title: str = "AI Pulse Digest"
    subject: str
    intro: str
    blurbs: list[NewsletterBlurbDTO]
    outro: str


# ==============================================================================
# API Request / Response DTOs
# ==============================================================================


class DraftNewsletterRequest(BaseModel):
    selected_article_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=5)
    rejected_article_ids: list[uuid.UUID] = Field(default_factory=list)
    suggested_top_n_ids: list[uuid.UUID] = Field(default_factory=list)
    edition_title: Optional[str] = None


class ApproveNewsletterRequest(BaseModel):
    structured_content: NewsletterStructuredContent


class SendNewsletterRequest(BaseModel):
    test_email: Optional[str] = None


class NewsletterItemResponse(BaseModel):
    id: uuid.UUID
    article_id: uuid.UUID
    rank_order: int
    theme: Optional[str] = None
    headline: str
    source_name: str
    source_url: str
    ai_generated_body: str
    human_approved_body: str
    was_edited: bool
    edit_ratio: float

    model_config = ConfigDict(from_attributes=True)


class NewsletterResponse(BaseModel):
    id: uuid.UUID
    edition_title: str
    subject: str
    structured_content: NewsletterStructuredContent
    full_markdown: str
    full_html: str
    status: str
    selected_count: int
    hitl_metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    approved_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    items: list[NewsletterItemResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class NewsletterSummaryDTO(BaseModel):
    id: uuid.UUID
    edition_title: str
    subject: str
    status: str
    selected_count: int
    created_at: datetime
    approved_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SendNewsletterResponse(BaseModel):
    status: str
    recipients_count: int
    recipients: list[str]
    is_test: bool = False


class SubscriberCreateRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=256)
    name: Optional[str] = Field(None, max_length=128)


class SubscriberResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
