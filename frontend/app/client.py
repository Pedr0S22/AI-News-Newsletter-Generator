import os
from typing import Any, Optional
import httpx

BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")


class APIClient:
    """Lightweight HTTP client communicating with the FastAPI backend."""

    def __init__(self, base_url: str = BACKEND_API_URL, timeout: int = 5):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def check_health(self) -> tuple[bool, Optional[dict[str, Any]], Optional[str]]:
        """Pings the backend /health endpoint."""
        url = f"{self.base_url}/health"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(url)
                if res.status_code == 200:
                    return True, res.json(), None
                return False, None, f"HTTP {res.status_code}: {res.text}"
        except Exception as e:
            return False, None, str(e)

    def trigger_ingestion(self) -> tuple[bool, Optional[dict[str, Any]], Optional[str]]:
        """Triggers article ingestion pipeline on the backend."""
        url = f"{self.base_url}/articles/ingest"
        try:
            with httpx.Client(timeout=300) as client:
                res = client.post(url)
                if res.status_code == 200:
                    return True, res.json(), None
                return False, None, f"HTTP {res.status_code}: {res.text}"
        except Exception as e:
            return False, None, str(e)

    def get_articles(self, limit: int = 50) -> list[dict[str, Any]]:
        """Fetches the list of ingested articles."""
        url = f"{self.base_url}/articles"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(url, params={"limit": limit})
                if res.status_code == 200:
                    return res.json()
                return []
        except Exception:
            return []


client = APIClient()
