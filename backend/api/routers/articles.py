from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.configs.database import get_db
from api.configs.logging import get_logger
from api.models.entities.article import Article
from api.models.dtos.article import ArticleResponse, IngestResponse
from api.services.ingestion.crawler_service import CrawlerService
from api.services.newsletter_service import NewsletterService

logger = get_logger(__name__)
router = APIRouter(tags=["Articles"])


@router.post("/ingest", response_model=IngestResponse)
async def trigger_ingestion(db: Session = Depends(get_db)):
    """Triggers Crawl4AI ingestion and automatically runs ADK Multi-Agent evaluation on new articles."""
    logger.info("HTTP POST /articles/ingest called.")
    crawler = CrawlerService(db=db)
    result = crawler.run_ingestion()
    logger.info(f"Ingestion finished: {result.ingested_count} new articles stored.")

    # Automatically evaluate all unevaluated articles (newly ingested + any backlog)
    nl_service = NewsletterService(db=db)
    eval_summary = await nl_service.evaluate_unevaluated_articles()
    result.evaluated_count = eval_summary.evaluated_count
    result.eliminated_count = (
        eval_summary.eliminated_topic_count + eval_summary.eliminated_duplicate_count
    )
    return result


@router.get("", response_model=list[ArticleResponse])
def list_articles(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Lists ingested articles ordered by published date descending."""
    logger.info(f"HTTP GET /articles called (skip={skip}, limit={limit}).")
    articles = (
        db.query(Article)
        .order_by(Article.published_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    logger.info(f"Returning {len(articles)} articles from database.")
    return articles
