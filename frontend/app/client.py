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
        """Pings the backend /health endpoint.

        Returns (is_healthy, payload, error_message).
        """
        url = f"{self.base_url}/health"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(url)
                if res.status_code == 200:
                    return True, res.json(), None
                return False, None, f"HTTP {res.status_code}: {res.text}"
        except Exception as e:
            return False, None, str(e)


client = APIClient()
