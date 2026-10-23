from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.configs.database import init_db
from api.configs.logging import setup_logging, get_logger
from api.routers.router import api_router

# Initialize structured logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing application lifecycle and database schema...")
    init_db()
    yield
    logger.info("Application shutting down...")


app = FastAPI(
    title="AI News Newsletter Generator API",
    version="0.1.0",
    lifespan=lifespan,
)

# Enable CORS for Streamlit frontend interaction
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount master application router
app.include_router(api_router)
