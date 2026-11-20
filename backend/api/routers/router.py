from fastapi import APIRouter
from api.routers import home, health, articles, agents, newsletters

api_router = APIRouter()

# Include modular sub-routers
api_router.include_router(home.router)
api_router.include_router(health.router)
api_router.include_router(articles.router, prefix="/articles")
api_router.include_router(agents.router, prefix="/agents")
api_router.include_router(newsletters.router, prefix="/newsletters")
