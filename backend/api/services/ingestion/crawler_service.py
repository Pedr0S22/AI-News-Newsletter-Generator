import re
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from api.configs.config import settings
from api.configs.logging import get_logger
from api.configs.sources import SOURCES
from api.models.entities.article import Article
from api.models.dtos.article import ArticleResponse, IngestResponse
from api.services.ingestion.crawl4ai_client import Crawl4AIClient
from api.services.ingestion.url_utils import normalize_url
from api.services.ingestion.date_parser import parse_published_date

logger = get_logger(__name__)


class CrawlerService:
    """Orchestrates link discovery, in-memory deduplication, content scraping,

    date auditing, and database persistence.
    """

    def __init__(self, db: Session, client: Crawl4AIClient = None):
        self.db = db
        self.client = client or Crawl4AIClient()

    def run_ingestion(self) -> IngestResponse:
        logger.info("Starting article ingestion pipeline across configured sources...")
        now = datetime.now(timezone.utc)

        total_scanned = 0
        total_skipped_existing = 0
        total_skipped_missing_date = 0
        total_skipped_too_old = 0
        saved_articles: list[Article] = []

        for source in SOURCES:
            logger.info(f"Crawling source '{source.name}' at hub URL: {source.hub_url}")
            discovered_raw_links = self.client.discover_links(source.hub_url)

            # 1. Normalize and filter candidate links matching pattern
            candidates = set()
            pattern = re.compile(source.article_url_pattern)

            for raw_link in discovered_raw_links:
                norm_link = normalize_url(raw_link, base_url=source.hub_url)
                if norm_link and pattern.match(norm_link):
                    candidates.add(norm_link)

            candidate_urls = list(candidates)
            total_scanned += len(candidate_urls)
            logger.info(f"Discovered {len(candidate_urls)} candidate article links for {source.name}.")

            if not candidate_urls:
                continue

            # 2. In-memory pre-deduplication against Database
            existing_urls_query = (
                self.db.query(Article.canonical_url, Article.original_url)
                .filter(
                    (Article.canonical_url.in_(candidate_urls))
                    | (Article.original_url.in_(candidate_urls))
                )
                .all()
            )
            existing_urls = {u for row in existing_urls_query for u in row if u}
            total_skipped_existing += len(existing_urls)

            new_urls = [u for u in candidate_urls if u not in existing_urls]
            logger.info(
                f"[{source.name}] {len(existing_urls)} URLs already exist in DB. Scraping {len(new_urls)} new URLs."
            )

            # 3. Scrape only the new URLs
            for url in new_urls:
                crawl_data = self.client.scrape_article(url)
                if not crawl_data:
                    logger.warning(f"Could not scrape content for '{url}'. Skipping.")
                    continue

                metadata = crawl_data.get("metadata") or {}
                raw_md = crawl_data.get("markdown")
                if isinstance(raw_md, dict):
                    markdown_content = raw_md.get("fit_markdown") or raw_md.get("raw_markdown") or ""
                elif isinstance(raw_md, str):
                    markdown_content = raw_md
                else:
                    markdown_content = ""

                # 4. Strict publication date parsing
                published_at = parse_published_date(metadata, markdown_content, url=url)
                if not published_at:
                    logger.warning(f"Skipping article from {source.name} (no publishedAt found): {url}")
                    total_skipped_missing_date += 1
                    continue

                # 5. Lookback date filter check
                age_days = (now - published_at).total_seconds() / 86400
                if age_days > settings.MAX_ARTICLE_AGE_DAYS:
                    logger.info(
                        f"Skipping article older than {settings.MAX_ARTICLE_AGE_DAYS} days "
                        f"({age_days:.1f} days old): {url}"
                    )
                    total_skipped_too_old += 1
                    continue

                # 6. Extract fields and build auditable entity
                raw_canonical = metadata.get("canonical") or metadata.get("og:url") or url
                canonical_url = normalize_url(raw_canonical, base_url=url) or url

                # Guard in case canonical_url redirected to an existing database entry
                if canonical_url in existing_urls or self.db.query(Article).filter(
                    (Article.canonical_url == canonical_url) | (Article.original_url == canonical_url)
                ).first():
                    total_skipped_existing += 1
                    continue

                title = metadata.get("title") or metadata.get("og:title") or url
                summary = metadata.get("description") or metadata.get("og:description") or None
                raw_author = metadata.get("author")
                author = raw_author.strip() if raw_author and str(raw_author).strip() else source.name

                article_record = Article(
                    source=source.name,
                    canonical_url=canonical_url,
                    original_url=url,
                    title=title.strip()[:512],
                    summary=summary.strip() if summary else None,
                    author=author[:256],
                    article=markdown_content,
                    published_at=published_at,
                )

                self.db.add(article_record)
                saved_articles.append(article_record)

        # 7. Commit new articles in a single transaction
        if saved_articles:
            self.db.commit()
            for art in saved_articles:
                self.db.refresh(art)

        logger.info(
            f"Ingestion complete. Scanned: {total_scanned}, Skipped Existing: {total_skipped_existing}, "
            f"Skipped Missing Date: {total_skipped_missing_date}, Skipped Too Old: {total_skipped_too_old}, "
            f"Ingested: {len(saved_articles)}."
        )

        return IngestResponse(
            status="success",
            scanned_links=total_scanned,
            skipped_existing_urls=total_skipped_existing,
            skipped_missing_date=total_skipped_missing_date,
            skipped_too_old=total_skipped_too_old,
            ingested_count=len(saved_articles),
            ingested_articles=[ArticleResponse.model_validate(a) for a in saved_articles],
        )
