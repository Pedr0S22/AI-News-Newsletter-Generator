# AI News Newsletter Generator
Multi-agent LLM system for AI news ingestion, fact-checking, hype scoring, and newsletter generation.

---

## Repository Architecture

The monorepo uses independent multi-stage Docker builds, separate environment configurations, and modern Docker Compose `include:` modularization.

```text
AI-News-Newsletter-Generator/
├── docker-compose.yml              # Root compose orchestrating backend & frontend via include:
├── README.md
│
├── backend/
│   ├── Dockerfile                  # 5-stage build
│   ├── docker-compose.yml          # Services: api (FastAPI), db (Postgres 17), crawl4ai (0.9.4)
│   ├── pyproject.toml              # Dependencies (FastAPI, SQLAlchemy, httpx, etc.)
│   ├── uv.lock                     # Locked dependency graph for frozen builds
│   ├── .env.example                # Backend environment template (Postgres, Crawl4AI, API keys)
│   ├── .env                        # Local / container backend environment variables
│   │
│   └── api/
│       ├── main.py                 # FastAPI application entrypoint with /health check
│       ├── configs/                # Configuration and database connection logic
│       ├── models/                 # Shared data schemas
│       ├── routers/                # API route definitions
│       └── services/               # Business logic
│           ├── newsletter_service.py
│           ├── ingestion/          # Web crawler/scraper logic
│           └── agents/             # Modular LLM agents (Hype, Fact, Theme, Dedup)
│               └── prompts/        # Decoupled agent system prompts
│
└── frontend/
    ├── Dockerfile                  # 5-stage build
    ├── docker-compose.yml          # Service: frontend (Streamlit)
    ├── pyproject.toml              # Dependencies (Streamlit, httpx, pandas)
    ├── uv.lock                     # Locked dependency graph for frozen builds
    ├── .env.example                # Frontend environment template
    ├── .env                        # Frontend environment variables
    │
    └── app/
        ├── app.py                  # Streamlit diagnostic & health dashboard
        ├── client.py               # HTTP client checking backend /health
        ├── components/             # Reusable UI widgets
        └── pages/                  # Multi-page views
```

---

## How to Run (Docker)

### 1. Configure Environments

Create the `.env` files from their respective templates:

### 2. Start the Entire Stack

From the repository root, start all services together (you can also start docker compose from backend or frontend):

```bash
docker compose up --build -d
```

To stop running the containers:

```bash
docker compose down # -v to delete database data
```

Docker Compose uses the `include:` directive to seamlessly start all 4 services across backend and frontend with built-in healthchecks:

| Service | Address | Description |
| :--- | :--- | :--- |
| **Frontend UI** | [http://localhost:8501](http://localhost:8501) | Streamlit diagnostic & newsletter dashboard |
| **Backend API** | [http://localhost:8000/docs](http://localhost:8000/docs) | Interactive OpenAPI docs |
| **API Health** | [http://localhost:8000/health](http://localhost:8000/health) | Backend healthcheck endpoint |
| **Crawl4AI API** | [http://localhost:11235/health](http://localhost:11235/health) | Web scraping engine healthcheck |
| **PostgreSQL 17** | `localhost:5432` | Containerized database (`ai_news`) |

---

### 3. Optional: Running Sub-stacks Independently

You can also run backend or frontend independently:

#### Backend only (API + Postgres + Crawl4AI):
```bash
cd backend
docker compose up --build
```

#### Frontend only:
```bash
cd frontend
docker compose up --build
```
