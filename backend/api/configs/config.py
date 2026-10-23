from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings strictly populated from environment variables."""

    DATABASE_URL: str
    CRAWL4AI_URL: str
    CRAWL4AI_API_TOKEN: str = ""
    MAX_ARTICLE_AGE_DAYS: int = 7

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
