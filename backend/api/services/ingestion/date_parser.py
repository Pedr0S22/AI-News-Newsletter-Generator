import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
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
    "article:modified_time",
    "og:updated_time",
    "dateModified",
]

# Regex fallback patterns for dates in text / snippet
FALLBACK_DATE_REGEX = [
    # YYYY-MM-DD or YYYY/MM/DD
    r"\b(20\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01]))\b",
    r"\b(20\d{2}/(?:0[1-9]|1[0-2])/(?:0[1-9]|[12]\d|3[01]))\b",
    # Month DD, YYYY (e.g. October 23, 2026 or Oct 23, 2026)
    r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?,?\s+20\d{2})\b",
    # DD Month YYYY (e.g. 23 October 2026 or 23 Oct 2026)
    r"\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20\d{2})\b",
    # DD-MM-YYYY or DD/MM/YYYY
    r"\b((?:0[1-9]|[12]\d|3[01])[/-](?:0[1-9]|1[0-2])[/-]20\d{2})\b",
]

# Regex for relative dates (e.g. "3 hours ago", "yesterday", "2 days ago")
RELATIVE_DATE_REGEX = [
    (r"\b(\d+)\s+min(?:ute)?s?\s+ago\b", "minutes"),
    (r"\b(\d+)\s+hours?\s+ago\b", "hours"),
    (r"\b(\d+)\s+days?\s+ago\b", "days"),
    (r"\byesterday\b", "yesterday"),
]

# Regex for date inside URL path (e.g. /2026/10/23/ or /2026-10-23-)
URL_DATE_REGEX = [
    r"/(20\d{2})/(0[1-9]|1[0-2])/([0-3]\d)/",
    r"/(20\d{2})-(0[1-9]|1[0-2])-([0-3]\d)",
    r"/(20\d{2})(0[1-9]|1[0-2])([0-3]\d)/",
]


def parse_published_date(
    metadata: Optional[dict] = None,
    text_snippet: str = "",
    url: str = "",
) -> Optional[datetime]:
    """Attempts to extract and parse the published timestamp.

    Checks:
    1. Direct metadata dictionary and nested JSON-LD/schema objects.
    2. HTML <time> tags in snippet.
    3. URL path embedded dates.
    4. Text regex patterns (US & European formats).
    5. Relative date mentions ("X hours ago", "yesterday").

    Returns timezone-aware UTC datetime or None if not discovered.
    """
    candidate_str: Optional[str] = None

    # 1. Search metadata dictionary (including nested JSON-LD)
    if metadata and isinstance(metadata, dict):
        candidate_str = _extract_from_metadata(metadata)

    # 2. Check HTML <time datetime="..."> in text snippet
    if not candidate_str and text_snippet:
        time_match = re.search(r"<time[^>]*datetime=[\"']([^\"']+)[\"']", text_snippet[:3000], re.IGNORECASE)
        if time_match:
            candidate_str = time_match.group(1).strip()

    # 3. Check dates embedded in the URL path
    if not candidate_str and url:
        for pattern in URL_DATE_REGEX:
            m = re.search(pattern, url)
            if m:
                year, month, day = m.group(1), m.group(2), m.group(3)
                candidate_str = f"{year}-{month}-{day}"
                break

    # 4. Fallback: regex search on article text / snippet
    if not candidate_str and text_snippet:
        for pattern in FALLBACK_DATE_REGEX:
            match = re.search(pattern, text_snippet[:3000], re.IGNORECASE)
            if match:
                candidate_str = match.group(1).strip()
                break

    # 5. Fallback: relative date expressions
    if not candidate_str and text_snippet:
        parsed_rel = _parse_relative_date(text_snippet[:1500])
        if parsed_rel:
            return parsed_rel

    if not candidate_str:
        return None

    # 6. Attempt parsing explicit string formats
    return _parse_datetime_string(candidate_str)


def _extract_from_metadata(metadata: dict) -> Optional[str]:
    """Recursively checks metadata dict and nested structures for date keys."""
    # Direct keys
    for key in DATE_METADATA_KEYS:
        val = metadata.get(key)
        if val and isinstance(val, str) and len(val.strip()) > 4:
            return val.strip()

    # Nested JSON-LD / schema structures
    for key in ("jsonld", "schema", "ld_json", "structured_data"):
        raw_val = metadata.get(key)
        if isinstance(raw_val, str):
            try:
                raw_val = json.loads(raw_val)
            except Exception:
                continue

        if isinstance(raw_val, dict):
            for sub_key in ("datePublished", "dateCreated", "dateModified", "uploadDate"):
                sub_val = raw_val.get(sub_key)
                if sub_val and isinstance(sub_val, str) and len(sub_val.strip()) > 4:
                    return sub_val.strip()
        elif isinstance(raw_val, list):
            for item in raw_val:
                if isinstance(item, dict):
                    for sub_key in ("datePublished", "dateCreated", "dateModified", "uploadDate"):
                        sub_val = item.get(sub_key)
                        if sub_val and isinstance(sub_val, str) and len(sub_val.strip()) > 4:
                            return sub_val.strip()

    return None


def _parse_relative_date(snippet: str) -> Optional[datetime]:
    now = datetime.now(timezone.utc)
    for pattern, unit in RELATIVE_DATE_REGEX:
        m = re.search(pattern, snippet, re.IGNORECASE)
        if not m:
            continue
        if unit == "yesterday":
            return (now - timedelta(days=1)).replace(microsecond=0)
        value = int(m.group(1))
        if unit == "minutes":
            return (now - timedelta(minutes=value)).replace(microsecond=0)
        elif unit == "hours":
            return (now - timedelta(hours=value)).replace(microsecond=0)
        elif unit == "days":
            return (now - timedelta(days=value)).replace(microsecond=0)
    return None


def _parse_datetime_string(date_str: str) -> Optional[datetime]:
    # Strip ordinal suffixes: 1st, 2nd, 3rd, 4th -> 1, 2, 3, 4
    clean_str = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", date_str.strip())
    clean_str = clean_str.replace("Z", "+00:00")

    # Try ISO-8601 (e.g. "2026-10-23T12:00:00Z" or "2026-10-23T12:00:00+00:00")
    try:
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # Standard explicit string formats
    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%B %d %Y",
        "%b %d %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%d %B, %Y",
        "%d %b, %Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(clean_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue

    logger.debug(f"Could not parse detected date string: '{date_str}'")
    return None
