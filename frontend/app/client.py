import os
from typing import Any, Optional
import httpx

BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")
MAILPIT_UI_URL = os.getenv("MAILPIT_UI_URL", "http://localhost:8025")


class APIClient:
    """HTTP client communicating with the FastAPI backend."""

    def __init__(self, base_url: str = BACKEND_API_URL, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def trigger_ingestion(self) -> tuple[bool, Optional[dict[str, Any]], Optional[str]]:
        """Triggers Crawl4AI ingestion + automatic ADK multi-agent evaluation."""
        url = f"{self.base_url}/articles/ingest"
        try:
            with httpx.Client(timeout=600) as client:
                res = client.post(url)
                if res.status_code == 200:
                    return True, res.json(), None
                return False, None, f"HTTP {res.status_code}: {res.text}"
        except Exception as e:
            return False, None, str(e)

    def trigger_evaluation(self) -> tuple[bool, Optional[dict[str, Any]], Optional[str]]:
        """Evaluates any pending unevaluated articles via Google ADK agents."""
        url = f"{self.base_url}/agents/evaluate"
        try:
            with httpx.Client(timeout=600) as client:
                res = client.post(url)
                if res.status_code == 200:
                    return True, res.json(), None
                return False, None, f"HTTP {res.status_code}: {res.text}"
        except Exception as e:
            return False, None, str(e)

    def get_rankings(self, top_n: int = 3) -> Optional[dict[str, Any]]:
        """Fetches ranked recommendations, candidate pool, and eliminated audit list."""
        url = f"{self.base_url}/agents/rankings"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(url, params={"top_n": top_n})
                if res.status_code == 200:
                    return res.json()
                return None
        except Exception:
            return None

    def get_analytics(self) -> Optional[dict[str, Any]]:
        """Fetches source reputation scores and HitL quality analytics."""
        url = f"{self.base_url}/agents/analytics"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(url)
                if res.status_code == 200:
                    return res.json()
                return None
        except Exception:
            return None

    def draft_newsletter(
        self,
        selected_article_ids: list[str],
        rejected_article_ids: list[str],
        suggested_top_n_ids: list[str],
        edition_title: str,
    ) -> tuple[bool, Optional[dict[str, Any]], Optional[str]]:
        """Submits HitL selections and synthesizes a Structured JSON newsletter draft."""
        url = f"{self.base_url}/newsletters/draft"
        payload = {
            "selected_article_ids": selected_article_ids,
            "rejected_article_ids": rejected_article_ids,
            "suggested_top_n_ids": suggested_top_n_ids,
            "edition_title": edition_title,
        }
        try:
            with httpx.Client(timeout=300) as client:
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    return True, res.json(), None
                return False, None, f"HTTP {res.status_code}: {res.text}"
        except Exception as e:
            return False, None, str(e)

    def list_newsletters(self) -> list[dict[str, Any]]:
        url = f"{self.base_url}/newsletters"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(url)
                if res.status_code == 200:
                    return res.json()
                return []
        except Exception:
            return []

    def get_newsletter(self, newsletter_id: str) -> Optional[dict[str, Any]]:
        url = f"{self.base_url}/newsletters/{newsletter_id}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(url)
                if res.status_code == 200:
                    return res.json()
                return None
        except Exception:
            return None

    def save_newsletter_draft(
        self, newsletter_id: str, structured_content: dict[str, Any]
    ) -> tuple[bool, Optional[dict[str, Any]], Optional[str]]:
        """Saves inline editorial edits to a newsletter without approving it."""
        url = f"{self.base_url}/newsletters/{newsletter_id}"
        try:
            with httpx.Client(timeout=30) as client:
                res = client.patch(url, json={"structured_content": structured_content})
                if res.status_code == 200:
                    return True, res.json(), None
                return False, None, f"HTTP {res.status_code}: {res.text}"
        except Exception as e:
            return False, None, str(e)

    def approve_newsletter(
        self,
        newsletter_id: str,
        structured_content: Optional[dict[str, Any]] = None,
    ) -> tuple[bool, Optional[dict[str, Any]], Optional[str]]:
        """Explicitly approves a newsletter edition and records Section 5 HitL metrics."""
        url = f"{self.base_url}/newsletters/{newsletter_id}/approve"
        payload = {"structured_content": structured_content} if structured_content is not None else {}
        try:
            with httpx.Client(timeout=30) as client:
                res = client.patch(url, json=payload)
                if res.status_code == 200:
                    return True, res.json(), None
                return False, None, f"HTTP {res.status_code}: {res.text}"
        except Exception as e:
            return False, None, str(e)

    def send_newsletter(
        self, newsletter_id: str, test_email: Optional[str] = None
    ) -> tuple[bool, Optional[dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/newsletters/{newsletter_id}/send"
        payload = {"test_email": test_email} if test_email else {}
        try:
            with httpx.Client(timeout=30) as client:
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    return True, res.json(), None
                return False, None, f"HTTP {res.status_code}: {res.text}"
        except Exception as e:
            return False, None, str(e)

    def list_subscribers(self) -> list[dict[str, Any]]:
        url = f"{self.base_url}/newsletters/subscribers"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(url)
                if res.status_code == 200:
                    return res.json()
                return []
        except Exception:
            return []

    def add_subscriber(
        self, email: str, name: Optional[str] = None
    ) -> tuple[bool, Optional[dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/newsletters/subscribers"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(url, json={"email": email, "name": name})
                if res.status_code == 200:
                    return True, res.json(), None
                return False, None, f"HTTP {res.status_code}: {res.text}"
        except Exception as e:
            return False, None, str(e)

    def remove_subscriber(self, subscriber_id: str) -> bool:
        url = f"{self.base_url}/newsletters/subscribers/{subscriber_id}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.delete(url)
                return res.status_code == 200
        except Exception:
            return False


client = APIClient()
