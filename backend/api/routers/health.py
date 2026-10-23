from fastapi import APIRouter
from api.configs.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """Service healthcheck endpoint."""
    logger.debug("Health check endpoint queried.")
    return {
        "status": "healthy",
        "service": "ai-news-backend",
        "version": "0.1.0",
    }
