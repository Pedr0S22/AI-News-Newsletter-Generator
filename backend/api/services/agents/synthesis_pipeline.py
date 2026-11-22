import json
import time
import uuid
from typing import Any
from google.adk.agents import Agent, LoopAgent, SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import exit_loop
from google.genai import types

from api.configs.config import settings
from api.configs.logging import get_logger
from api.models.dtos.newsletter import NewsletterBlurbDTO, NewsletterStructuredContent
from api.services.agents.iaedu_llm import extract_json_object, get_writer_llm
from api.services.agents.prompts.templates import (
    CRITIC_AGENT_PROMPT,
    REVISER_AGENT_PROMPT,
    WRITER_AGENT_PROMPT,
)

logger = get_logger(__name__)

_APP_NAME = "ai_news_synthesizer"
_MAX_BODY_CHARS_PER_ARTICLE = 5500


async def synthesize_newsletter_draft(
    curated_articles: list[dict[str, Any]],
    edition_title: str,
) -> NewsletterStructuredContent:
    """Runs the Google ADK SequentialAgent + Reflection LoopAgent (Writer -> Critic <-> Reviser).

    Directly mirrors the DSPT Agentic AI design pattern (Cell 30) and returns a strictly
    validated Structured JSON newsletter (`edition_title`, `subject`, `intro`, `blurbs`, `outro`)
    containing zero internal evaluation scores.
    """
    llm = get_writer_llm()

    writer_agent = Agent(
        name="journalistic_writer",
        model=llm,
        output_key="draft",
        instruction=WRITER_AGENT_PROMPT,
    )
    critic_agent = Agent(
        name="editorial_critic",
        model=llm,
        output_key="feedback",
        tools=[exit_loop],
        instruction=CRITIC_AGENT_PROMPT,
    )
    reviser_agent = Agent(
        name="editorial_reviser",
        model=llm,
        output_key="draft",
        instruction=REVISER_AGENT_PROMPT,
    )

    reflection_loop = LoopAgent(
        name="editorial_reflection_loop",
        max_iterations=settings.REFLECTION_MAX_ITERATIONS,
        sub_agents=[critic_agent, reviser_agent],
    )
    newsletter_pipeline = SequentialAgent(
        name="newsletter_synthesis_pipeline",
        sub_agents=[writer_agent, reflection_loop],
    )

    # Prepare clean grounded input payload for the Writer (NO internal scores passed!)
    clean_payload = {
        "edition_title": edition_title,
        "approved_articles": [
            {
                "article_id": str(item["article_id"]),
                "rank_order": idx + 1,
                "theme": item.get("theme") or "AI News",
                "title": item["title"],
                "source_name": item["source_name"],
                "source_url": item["source_url"],
                "author": item.get("author") or item["source_name"],
                "published_at": item.get("published_at", ""),
                "article_text": (item.get("article_text") or "")[:_MAX_BODY_CHARS_PER_ARTICLE],
            }
            for idx, item in enumerate(curated_articles)
        ],
    }

    prompt = (
        "Draft the newsletter edition as a single Structured JSON object from these "
        f"human-approved articles:\n\n{json.dumps(clean_payload, indent=2)}"
    )

    session_service = InMemorySessionService()
    session_id = f"synth_{uuid.uuid4().hex}"
    user_id = "editorial_system"

    runner = Runner(
        agent=newsletter_pipeline,
        app_name=_APP_NAME,
        session_service=session_service,
        auto_create_session=True,
    )

    provider = (settings.WRITER_LLM_PROVIDER or "iaedu").strip().lower()
    model_desc = "iaedu/gpt-5.5" if provider == "iaedu" else f"ollama/{settings.OLLAMA_MODEL}"
    t_start = time.monotonic()
    logger.info(
        f"[Synthesis] Starting ADK Writer + Reflection pipeline for {len(curated_articles)} "
        f"curated articles via {model_desc}..."
    )
    reflection_round = 0
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        for call in event.get_function_calls():
            logger.info(f"[Synthesis] [{event.author}] Tool called -> {call.name}({call.args})")

        if event.is_final_response() and event.content and event.content.parts:
            text = "".join(p.text or "" for p in event.content.parts).strip()
            if event.author == "journalistic_writer":
                logger.info(
                    f"[Synthesis] Writer draft generated ({len(text)} chars) "
                    f"[{time.monotonic() - t_start:.1f}s]"
                )
            elif event.author == "editorial_critic" and text:
                reflection_round += 1
                logger.info(
                    f"[Synthesis] Critic round #{reflection_round} feedback: {text[:220]}"
                )
            elif event.author == "editorial_reviser":
                logger.info(
                    f"[Synthesis] Reviser round #{reflection_round} updated draft "
                    f"({len(text)} chars) [{time.monotonic() - t_start:.1f}s]"
                )

    logger.info(f"[Synthesis] Pipeline finished in {time.monotonic() - t_start:.1f}s.")

    session = await session_service.get_session(
        app_name=_APP_NAME, user_id=user_id, session_id=session_id
    )
    raw_draft = str(session.state.get("draft", "")) if session and session.state else ""
    parsed = extract_json_object(raw_draft)

    if parsed:
        try:
            structured = NewsletterStructuredContent.model_validate(parsed)
            # Enforce authoritative metadata (source URLs, IDs, and rank order) defensively
            by_id = {str(a["article_id"]): a for a in curated_articles}
            fixed_blurbs: list[NewsletterBlurbDTO] = []
            for idx, blurb in enumerate(structured.blurbs):
                src = by_id.get(blurb.article_id) or (
                    curated_articles[idx] if idx < len(curated_articles) else None
                )
                if src:
                    fixed_blurbs.append(
                        NewsletterBlurbDTO(
                            article_id=str(src["article_id"]),
                            rank_order=idx + 1,
                            theme=src.get("theme") or blurb.theme or "AI News",
                            headline=blurb.headline.strip(),
                            body=blurb.body.strip(),
                            source_name=src["source_name"],
                            source_url=src["source_url"],
                        )
                    )
            if fixed_blurbs:
                structured.edition_title = edition_title
                structured.blurbs = fixed_blurbs
                return structured
        except Exception as exc:
            logger.warning(f"Structured newsletter validation fallback triggered: {exc}")

    # Deterministic graceful fallback if LLM returned malformed JSON
    logger.warning("Using deterministic fallback newsletter structure from curated summaries.")
    fallback_blurbs = [
        NewsletterBlurbDTO(
            article_id=str(item["article_id"]),
            rank_order=idx + 1,
            theme=item.get("theme") or "AI News",
            headline=item["title"],
            body=item.get("summary") or (item.get("article_text") or "")[:400],
            source_name=item["source_name"],
            source_url=item["source_url"],
        )
        for idx, item in enumerate(curated_articles)
    ]
    top_headline = fallback_blurbs[0].headline if fallback_blurbs else edition_title
    return NewsletterStructuredContent(
        edition_title=edition_title,
        subject=f"{edition_title}: {top_headline[:72]}",
        intro="Here is our curated briefing covering the most verifiable AI engineering and research developments.",
        blurbs=fallback_blurbs,
        outro="Thank you for reading. Stay tuned for our next curated AI briefing.",
    )
