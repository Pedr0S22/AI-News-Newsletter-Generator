from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings strictly populated from environment variables."""

    # Core Infrastructure
    DATABASE_URL: str
    CRAWL4AI_URL: str
    CRAWL4AI_API_TOKEN: str = ""
    MAX_ARTICLE_AGE_DAYS: int = 7

    # IAedu GPT-5.5 API
    CHATGPT_55_ENDPOINT: str = ""
    CHATGPT_55_API_KEY: str = ""
    CHATGPT_55_CHANNEL_ID: str = ""

    # Hybrid LLM Provider Routing (ollama | iaedu)
    EVAL_LLM_PROVIDER: str = "ollama"
    WRITER_LLM_PROVIDER: str = "iaedu"

    # Local Ollama (Host GPU)
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434/v1"
    OLLAMA_MODEL: str = "gemma4:e4b"
    OLLAMA_REASONING_EFFORT: str = "none"

    # Multi-Agent Evaluation & Ranking
    DEFAULT_TOP_N: int = 3
    MAX_TOP_N: int = 5
    WEIGHT_FACTUALITY: float = 0.5
    WEIGHT_HYPE: float = 0.5
    REPUTATION_DEFAULT: float = 1.0
    REPUTATION_MIN: float = 0.3
    REPUTATION_MAX: float = 1.5
    AGENT_MAX_CONCURRENCY: int = 1
    REFLECTION_MAX_ITERATIONS: int = 3

    # Newsletter & Email Delivery (Mailpit SMTP)
    NEWSLETTER_DEFAULT_TITLE: str = "AI Pulse Digest"
    SMTP_HOST: str = "mailpit"
    SMTP_PORT: int = 1025
    SMTP_FROM_EMAIL: str = "newsletter@aipulse.local"
    SMTP_FROM_NAME: str = "AI Pulse Digest"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
