import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from api.configs.database import Base


class ArticleEvaluation(Base):
    """Explainable multi-agent audit scores, rationales, and ranking for each article."""

    __tablename__ = "article_evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    article_id = Column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    # 1. Topic Agent (AI relevance filter + theme label)
    is_ai_topic = Column(Boolean, nullable=False, default=True)
    primary_theme = Column(String(128), nullable=True)
    topic_reason = Column(Text, nullable=True)

    # 2. Hype Agent (1-10, lower is better; groundedness = 11 - hype_score)
    hype_score = Column(Float, nullable=True)
    groundedness_score = Column(Float, nullable=True)
    hype_reason = Column(Text, nullable=True)

    # 3. Factuality Agent (1-10, higher is better, corroborated against external/DB sources)
    factuality_score = Column(Float, nullable=True)
    factuality_reason = Column(Text, nullable=True)
    verification_sources = Column(JSONB, nullable=False, default=list)

    # 4. Deduplication Agent (compared against all articles in DB)
    is_duplicate = Column(Boolean, nullable=False, default=False)
    duplicate_of_article_id = Column(UUID(as_uuid=True), nullable=True)
    dedup_reason = Column(Text, nullable=True)

    # 5. Final Ranking Score = weighted_subscore * reputation_snapshot
    weighted_subscore = Column(Float, nullable=False, default=0.0)
    reputation_snapshot = Column(Float, nullable=False, default=1.0)
    final_ranking_score = Column(Float, nullable=False, default=0.0, index=True)

    # Lifecycle status:
    # ranked | eliminated_topic | eliminated_duplicate | human_approved | human_rejected | published
    status = Column(String(32), nullable=False, default="ranked", index=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    article = relationship("Article", backref="evaluation")
