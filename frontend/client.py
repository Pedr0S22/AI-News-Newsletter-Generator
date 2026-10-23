import os
from typing import Any, Optional
import httpx

BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000/api/v1")


class APIClient:
    """HTTP client wrapper communicating with the FastAPI backend."""

    def __init__(self, base_url: str = BACKEND_API_URL, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        raise NotImplementedError("The APIClient class is not yet fully implemented.")

    def check_health(self) -> bool:
        try:
            url = self.base_url.replace("/api/v1", "/health")
            with httpx.Client(timeout=3) as client:
                res = client.get(url)
                return res.status_code == 200
        except Exception:
            return False

client = APIClient()
