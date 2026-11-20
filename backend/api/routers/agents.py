from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.configs.config import settings
from api.configs.database import get_db
from api.configs.logging import get_logger
from api.models.dtos.evaluation import (
    AnalyticsResponse,
    EvaluationRunResponse,
    RankingsResponse,
)
from api.services.newsletter_service import NewsletterService

logger = get_logger(__name__)
router = APIRouter(tags=["Agents & Rankings"])


@router.post("/evaluate", response_model=EvaluationRunResponse)
async def evaluate_articles(db: Session = Depends(get_db)):
    """Evaluates all unevaluated articles using the Google ADK Multi-Agent pipeline."""
    logger.info("HTTP POST /agents/evaluate called.")
    service = NewsletterService(db=db)
    return await service.evaluate_unevaluated_articles()


@router.get("/rankings", response_model=RankingsResponse)
def get_rankings(
    top_n: int = Query(
        default=settings.DEFAULT_TOP_N,
        ge=1,
        le=settings.MAX_TOP_N,
    ),
    db: Session = Depends(get_db),
):
    """Returns Top-N recommended stories, candidate pool, and eliminated audit entries."""
    service = NewsletterService(db=db)
    return service.get_rankings(top_n=top_n)


@router.get("/analytics", response_model=AnalyticsResponse)
def get_analytics(db: Session = Depends(get_db)):
    """Returns dynamic Source Reputation scores and Proposal Section 5 HitL metrics."""
    service = NewsletterService(db=db)
    return service.get_analytics()
