import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from api.configs.database import Base


class Newsletter(Base):
    """Generated newsletter edition storing Structured JSON, rendered HTML/Markdown, and HitL metrics."""

    __tablename__ = "newsletters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    edition_title = Column(String(256), nullable=False)
    subject = Column(String(512), nullable=False)

    # Structured JSON: {edition_title, subject, intro, blurbs: [...], outro}
    structured_content = Column(JSONB, nullable=False)
    full_markdown = Column(Text, nullable=False)
    full_html = Column(Text, nullable=False)

    # Lifecycle: draft | approved | sent
    status = Column(String(32), nullable=False, default="draft", index=True)
    selected_count = Column(Integer, nullable=False, default=0)

    # Section 5 Evaluation Metrics (top_n_retention_rate, reordered, avg_edit_ratio, etc.)
    hitl_metrics = Column(JSONB, nullable=False, default=dict)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)

    items = relationship(
        "NewsletterItem",
        back_populates="newsletter",
        cascade="all, delete-orphan",
        order_by="NewsletterItem.rank_order",
    )


class NewsletterItem(Base):
    """Individual curated story inside a newsletter edition, tracking AI vs Human edits."""

    __tablename__ = "newsletter_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    newsletter_id = Column(
        UUID(as_uuid=True),
        ForeignKey("newsletters.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    article_id = Column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    rank_order = Column(Integer, nullable=False)
    theme = Column(String(128), nullable=True)
    headline = Column(String(512), nullable=False)
    source_name = Column(String(128), nullable=False)
    source_url = Column(String(1024), nullable=False)

    ai_generated_body = Column(Text, nullable=False)
    human_approved_body = Column(Text, nullable=False)
    was_edited = Column(Boolean, nullable=False, default=False)
    edit_ratio = Column(Float, nullable=False, default=0.0)

    newsletter = relationship("Newsletter", back_populates="items")


class Subscriber(Base):
    """Newsletter email subscriber managed from the Admin Dashboard."""

    __tablename__ = "subscribers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(256), unique=True, index=True, nullable=False)
    name = Column(String(128), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
