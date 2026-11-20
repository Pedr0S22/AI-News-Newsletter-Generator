from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from api.configs.database import Base


class SourceReputation(Base):
    """Tracks dynamic source trust/reputation updated via Human-in-the-Loop feedback."""

    __tablename__ = "source_reputations"

    source_name = Column(String(128), primary_key=True)
    reputation_score = Column(Float, nullable=False, default=1.0)
    accepted_count = Column(Integer, nullable=False, default=0)
    rejected_count = Column(Integer, nullable=False, default=0)
    edited_count = Column(Integer, nullable=False, default=0)
    promoted_count = Column(Integer, nullable=False, default=0)
    total_evaluated = Column(Integer, nullable=False, default=0)
    history = Column(JSONB, nullable=False, default=list)

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
