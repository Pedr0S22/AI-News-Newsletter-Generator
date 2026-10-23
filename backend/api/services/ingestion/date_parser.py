import re
from datetime import datetime, timezone
from typing import Optional
from api.configs.logging import get_logger

logger = get_logger(__name__)

# Common metadata keys representing publication dates
DATE_METADATA_KEYS = [
    "article:published_time",
    "og:article:published_time",
    "datePublished",
    "published_time",
    "publishedAt",
    "publish_date",
    "release_date",
    "parsely-pub-date",
    "sailthru.date",
    "dc.date",
    "pubdate",
    "date",
]

# Regex fallback patterns for dates in text
FALLBACK_DATE_REGEX = [
    r"\b(20\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01]))\b",  # YYYY-MM-DD
    r"\b(20\d{2}/(?:0[1-9]|1[0-2])/(?:0[1-9]|[12]\d|3[01]))\b",  # YYYY/MM/DD
    r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2})\b",  # Month DD, YYYY
]


def parse_published_date(metadata: dict, text_snippet: str = "") -> Optional[datetime]:
    """Attempts to extract and parse the published timestamp.

    Checks page metadata first, then falls back to regex matching on text.
    Returns timezone-aware UTC datetime or None if not discovered.
    """
    candidate_str: Optional[str] = None

    # 1. Search metadata dictionary
    if metadata and isinstance(metadata, dict):
        for key in DATE_METADATA_KEYS:
            val = metadata.get(key)
            if val and isinstance(val, str) and len(val.strip()) > 4:
                candidate_str = val.strip()
                break

    # 2. Fallback: regex search on article text / snippet
    if not candidate_str and text_snippet:
        for pattern in FALLBACK_DATE_REGEX:
            match = re.search(pattern, text_snippet[:2000], re.IGNORECASE)
            if match:
                candidate_str = match.group(1).strip()
                break

    if not candidate_str:
        return None

    # 3. Attempt parsing formats
    return _parse_datetime_string(candidate_str)


def _parse_datetime_string(date_str: str) -> Optional[datetime]:
    # Try ISO-8601 (e.g., "2025-01-15T12:00:00Z" or "2025-01-15T12:00:00+00:00")
    clean_str = date_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # Try common explicit string formats
    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%B %d %Y",
        "%b %d %Y",
        "%d %B %Y",
        "%d %b %Y",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue

    logger.debug(f"Could not parse detected date string: '{date_str}'")
    return None
