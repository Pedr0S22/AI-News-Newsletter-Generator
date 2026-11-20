import re
import threading
import time
import uuid
from typing import Any, Optional
from sqlalchemy.orm import Session

from api.configs.logging import get_logger
from api.models.entities.article import Article

logger = get_logger(__name__)

_SEARCH_LOCK = threading.Lock()
_LAST_SEARCH_TS = 0.0
_MIN_SEARCH_INTERVAL_SEC = 0.85

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "over", "more",
    "have", "will", "your", "their", "about", "what", "when", "where", "which",
    "how", "are", "was", "were", "been", "being", "its", "our", "new", "using",
    "openai", "anthropic", "google", "deepmind", "hugging", "face", "bbc", "news",
    "blog", "part", "models", "model",
}


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]{3,}", (text or "").lower())
    return {w for w in words if w not in _STOPWORDS}


def search_duckduckgo(query: str, max_results: int = 4) -> list[dict[str, str]]:
    """Queries DuckDuckGo (ddgs) with gentle pacing for independent web corroboration snippets."""
    global _LAST_SEARCH_TS
    results: list[dict[str, str]] = []

    # Strip trailing source suffixes and noisy punctuation; keep concise query for better hit rate
    clean_query = re.sub(
        r"\s*[\|\\—–-]\s*(OpenAI|Anthropic|Google DeepMind|BBC|Hugging Face).*$",
        "",
        query or "",
    ).strip()
    clean_query = re.sub(r"[^\w\s\-]", " ", clean_query)
    words = clean_query.split()
    if len(words) > 9:
        clean_query = " ".join(words[:9])
    if not clean_query:
        return results

    try:
        from ddgs import DDGS

        with _SEARCH_LOCK:
            elapsed = time.monotonic() - _LAST_SEARCH_TS
            if elapsed < _MIN_SEARCH_INTERVAL_SEC:
                time.sleep(_MIN_SEARCH_INTERVAL_SEC - elapsed)
            _LAST_SEARCH_TS = time.monotonic()

            with DDGS() as ddgs:
                raw_hits = list(ddgs.text(clean_query, max_results=max_results))

        for hit in raw_hits:
            url = hit.get("href") or hit.get("url") or ""
            title = hit.get("title") or ""
            snippet = hit.get("body") or hit.get("snippet") or ""
            if url and title:
                results.append(
                    {
                        "title": title.strip()[:200],
                        "url": url.strip(),
                        "snippet": snippet.strip()[:300],
                        "origin": "web",
                    }
                )
    except Exception as exc:
        msg = str(exc)
        if "No results found" in msg:
            logger.debug(f"No external web hits indexed yet for '{clean_query[:60]}'; using DB + primary source.")
        else:
            logger.warning(f"Web corroboration lookup skipped for '{clean_query[:60]}': {msg}")

    return results


def find_related_db_articles(
    target_article: Article,
    all_articles: list[Article],
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Finds related articles already in PostgreSQL via lexical overlap."""
    target_tokens = _tokenize(f"{target_article.title} {target_article.summary or ''}")
    if not target_tokens:
        return []

    scored: list[tuple[float, Article]] = []
    for other in all_articles:
        if other.id == target_article.id:
            continue
        other_tokens = _tokenize(f"{other.title} {other.summary or ''}")
        if not other_tokens:
            continue
        overlap = len(target_tokens & other_tokens)
        if overlap == 0:
            continue
        jaccard = overlap / max(len(target_tokens | other_tokens), 1)
        scored.append((jaccard, other))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    related: list[dict[str, Any]] = []
    for _, art in scored[:top_k]:
        related.append(
            {
                "title": art.title,
                "url": art.canonical_url,
                "snippet": (art.summary or "")[:250],
                "origin": "database",
            }
        )
    return related


def gather_corroboration_evidence(
    target_article: Article,
    all_articles: list[Article],
) -> list[dict[str, str]]:
    """Gathers independent DuckDuckGo web hits + related DB articles for Factuality verification."""
    web_hits = search_duckduckgo(target_article.title, max_results=4)
    # Exclude exact self-URL from web hits so corroboration reflects external coverage
    target_norm = (target_article.canonical_url or "").rstrip("/").lower()
    external_hits = [
        h for h in web_hits if h["url"].rstrip("/").lower() != target_norm
    ][:3]

    db_hits = find_related_db_articles(target_article, all_articles, top_k=3)
    return external_hits + db_hits


def select_dedup_candidates(
    target_article: Article,
    all_existing_articles: list[Article],
    max_candidates: int = 25,
) -> list[dict[str, Any]]:
    """Selects comparison articles from ALL articles in DB for semantic deduplication.

    If total existing articles <= max_candidates, includes EVERY article in DB.
    Otherwise includes the top lexically overlapping + most recent articles.
    """
    others = [a for a in all_existing_articles if a.id != target_article.id]
    if not others:
        return []

    if len(others) <= max_candidates:
        chosen = sorted(others, key=lambda a: a.published_at, reverse=True)
    else:
        target_tokens = _tokenize(f"{target_article.title} {target_article.summary or ''}")
        scored = []
        for art in others:
            other_tokens = _tokenize(f"{art.title} {art.summary or ''}")
            overlap = len(target_tokens & other_tokens)
            score = overlap / max(len(target_tokens | other_tokens), 1) if target_tokens else 0.0
            scored.append((score, art))
        scored.sort(key=lambda pair: (pair[0], pair[1].published_at), reverse=True)
        top_by_sim = [art for _, art in scored[:18]]
        seen_ids = {a.id for a in top_by_sim}
        recent_extra = [
            a for a in sorted(others, key=lambda x: x.published_at, reverse=True)
            if a.id not in seen_ids
        ][: max_candidates - len(top_by_sim)]
        chosen = top_by_sim + recent_extra

    return [
        {
            "article_id": str(a.id),
            "source": a.source,
            "title": a.title,
            "summary": (a.summary or "")[:240],
            "published_at": a.published_at.strftime("%Y-%m-%d") if a.published_at else "",
        }
        for a in chosen
    ]
