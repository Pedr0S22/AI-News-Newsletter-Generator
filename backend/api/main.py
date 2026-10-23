from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="AI News Newsletter Generator API",
    version="0.1.0",
)

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
def health_check():
    """Service healthcheck endpoint."""
    return {
        "status": "healthy",
        "service": "ai-news-backend",
        "version": "0.1.0",
    }


@app.get("/", tags=["Root"])
def root():
    return {
        "message": "AI News Newsletter Generator API is running",
        "docs_url": "/docs",
        "health_url": "/health",
    }
