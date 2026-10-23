from typing import Any, Optional
import httpx
from api.configs.config import settings
from api.configs.logging import get_logger

logger = get_logger(__name__)


class Crawl4AIClient:
    """HTTP client wrapper communicating with the containerized Crawl4AI REST service."""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None, timeout: int = 45):
        self.base_url = (base_url or settings.CRAWL4AI_URL).rstrip("/")
        self.token = token or settings.CRAWL4AI_API_TOKEN
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def crawl_url(self, url: str, exclude_chrome: bool = False) -> Optional[dict[str, Any]]:
        """Sends a URL to Crawl4AI /crawl and returns the first CrawlResult dictionary.

        When exclude_chrome=True, instructs Crawl4AI to exclude nav, footer,
        header, and overlay elements to extract clean article markdown.
        """
        endpoint = f"{self.base_url}/crawl"
        crawler_config = {}
        if exclude_chrome:
            crawler_config = {
                "excluded_tags": ["nav", "footer", "header", "aside", "form"],
                "remove_overlay_elements": True,
            }

        payload: dict[str, Any] = {
            "urls": [url],
            "priority": 10,
        }
        if crawler_config:
            payload["crawler_config"] = crawler_config

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(endpoint, json=payload, headers=self.headers)
                if response.status_code >= 400:
                    logger.error(
                        f"Crawl4AI returned HTTP {response.status_code} for '{url}'. "
                        f"Response body: {response.text}"
                    )
                response.raise_for_status()
                data = response.json()

            results = data.get("results")
            if not results or not isinstance(results, list):
                logger.error(f"Crawl4AI returned invalid or empty results array for '{url}': {data}")
                return None

            first_result = results[0]
            if not first_result.get("success", False):
                logger.warning(
                    f"Crawl4AI crawl failed for '{url}': {first_result.get('error_message')}"
                )
                return None

            return first_result

        except Exception as e:
            logger.error(f"Crawl4AI request failed for URL '{url}': {e}")
            return None

    def discover_links(self, hub_url: str) -> list[str]:
        """Crawls a hub page and extracts discovered internal article links."""
        crawl_result = self.crawl_url(hub_url)
        if not crawl_result:
            return []

        links_obj = crawl_result.get("links", {})
        if isinstance(links_obj, dict):
            internal_links = links_obj.get("internal", [])
            urls = []
            for item in internal_links:
                if isinstance(item, dict) and "href" in item:
                    urls.append(item["href"])
                elif isinstance(item, str):
                    urls.append(item)
            return urls

        return []

    def scrape_article(self, url: str) -> Optional[dict[str, Any]]:
        """Scrapes full article content, clean Markdown, and metadata."""
        return self.crawl_url(url, exclude_chrome=True)
