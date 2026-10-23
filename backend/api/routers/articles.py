from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.configs.database import get_db
from api.configs.logging import get_logger
from api.models.entities.article import Article
from api.models.dtos.article import ArticleResponse, IngestResponse
from api.services.ingestion.crawler_service import CrawlerService

logger = get_logger(__name__)
router = APIRouter(tags=["Articles"])


@router.post("/ingest", response_model=IngestResponse)
def trigger_ingestion(db: Session = Depends(get_db)):
    """Triggers the Crawl4AI article ingestion and deduplication pipeline."""
    logger.info("HTTP POST /articles/ingest called.")
    service = CrawlerService(db=db)
    result = service.run_ingestion()
    logger.info(f"Ingestion finished: {result.ingested_count} new articles stored.")
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
