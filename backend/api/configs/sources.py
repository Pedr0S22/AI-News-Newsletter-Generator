from pydantic import BaseModel


class NewsSource(BaseModel):
    name: str
    hub_url: str
    article_url_pattern: str


# Configured AI news sources - strictly matching HTTPS URLs
SOURCES: list[NewsSource] = [
    NewsSource(
        name="OpenAI News",
        hub_url="https://openai.com/news/",
        article_url_pattern=r"^https://openai\.com/(index|news)/[a-zA-Z0-9_-]+/?$",
    ),
    NewsSource(
        name="Anthropic News",
        hub_url="https://www.anthropic.com/news",
        article_url_pattern=r"^https://www\.anthropic\.com/news/[a-zA-Z0-9_-]+/?$",
    ),
    NewsSource(
        name="Google DeepMind",
        hub_url="https://deepmind.google/discover/blog/",
        article_url_pattern=r"^https://deepmind\.google/discover/blog/[a-zA-Z0-9_-]+/?$",
    ),
]
