import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode, urljoin

# Tracking query parameters to strip
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "_hsenc",
    "_hsmi",
    "trk",
}


def normalize_url(url: str, base_url: str = None) -> str:
    """Normalizes a URL by resolving relative paths, removing fragments,

    stripping tracking query parameters, and normalizing trailing slashes.
    """
    if not url:
        return ""

    # Resolve relative URLs if base_url is supplied
    if base_url:
        url = urljoin(base_url, url)

    parsed = urlparse(url)

    # Lowercase scheme and netloc
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Filter out tracking query parameters
    filtered_query_params = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(filtered_query_params)

    # Normalize path: remove trailing slash if path is longer than root '/'
    path = parsed.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Reconstruct URL without fragment (#...)
    normalized = urlunparse((scheme, netloc, path, parsed.params, query, ""))
    return normalized
