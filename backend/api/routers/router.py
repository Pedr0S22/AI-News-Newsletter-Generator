from fastapi import APIRouter
from api.routers import home, health, articles

api_router = APIRouter()

# Include modular sub-routers
api_router.include_router(home.router)
api_router.include_router(health.router)
api_router.include_router(articles.router, prefix="/articles")
