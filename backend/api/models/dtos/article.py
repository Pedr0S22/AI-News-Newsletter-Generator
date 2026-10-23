import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ArticleResponse(BaseModel):
    """Data Transfer Object for reading an Article entity."""

    id: uuid.UUID
    source: str
    canonical_url: str
    original_url: Optional[str] = None
    title: str
    summary: Optional[str] = None
    author: Optional[str] = None
    article: str
    published_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IngestResponse(BaseModel):
    """Data Transfer Object returned by the ingestion trigger endpoint."""

    status: str
    scanned_links: int
    skipped_existing_urls: int
    skipped_missing_date: int
    skipped_too_old: int
    ingested_count: int
    ingested_articles: list[ArticleResponse]
