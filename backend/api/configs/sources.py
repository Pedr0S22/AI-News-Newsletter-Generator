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
        hub_url="https://anthropic.com/news",
        article_url_pattern=r"^https://(www\.)?anthropic\.com/news/[a-zA-Z0-9_-]+/?$",
    ),
    NewsSource(
        name="Google DeepMind",
        hub_url="https://deepmind.google/discover/blog/",
        article_url_pattern=r"^https://deepmind\.google/(discover/)?blog/[a-zA-Z0-9_-]+/?$",
    ),
    NewsSource(
        name="Google AI Blog",
        hub_url="https://blog.google/innovation-and-ai/models-and-research/",
        article_url_pattern=r"^https://blog\.google/innovation-and-ai/models-and-research/[a-zA-Z0-9_-]+/?$",
    ),
    NewsSource(
        name="Google AI Blog",
        hub_url="https://blog.google/innovation-and-ai/",
        article_url_pattern=r"^https://blog\.google/innovation-and-ai/[a-zA-Z0-9_-]+/?$",
    ),
    NewsSource(
        name="BBC AI News",
        hub_url="https://www.bbc.com/news/topics/ce1qrvleleqt",
        article_url_pattern=r"^https://www\.bbc\.com/news/(articles/|topics/ce1qrvleleqt/)[a-zA-Z0-9_-]+/?$",
    ),
    NewsSource(
        name="Hugging Face Blog",
        hub_url="https://huggingface.co/blog",
        article_url_pattern=r"^https://huggingface\.co/blog/[a-zA-Z0-9_-]+/?$"
    )
]
