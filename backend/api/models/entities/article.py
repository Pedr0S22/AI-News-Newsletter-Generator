import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from api.configs.database import Base


class Article(Base):
    """Auditable PostgreSQL entity for scraped news articles."""

    __tablename__ = "articles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(128), nullable=False)
    canonical_url = Column(String(1024), unique=True, index=True, nullable=False)
    title = Column(String(512), nullable=False)
    summary = Column(Text, nullable=True)
    author = Column(String(256), nullable=True)
    article = Column(Text, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=False)

    # Auditable timestamps
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
