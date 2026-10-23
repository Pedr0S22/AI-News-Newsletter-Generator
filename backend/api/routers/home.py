from fastapi import APIRouter

router = APIRouter(tags=["Home"])


@router.get("/")
def home():
    """Root entrypoint displaying API service information."""
    return {
        "message": "AI News Newsletter Generator API is running",
        "docs_url": "/docs",
        "health_url": "/health",
        "ingest_url": "/articles/ingest",
    }
