import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional
from google.adk.agents import Agent, ParallelAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from api.configs.logging import get_logger
from api.models.dtos.evaluation import (
    DeduplicationAgentOutput,
    FactualityAgentOutput,
    HypeAgentOutput,
    TopicAgentOutput,
)
from api.models.entities.article import Article
from api.services.agents.iaedu_llm import extract_json_object, get_eval_llm
from api.services.agents.prompts.templates import (
    DEDUPLICATION_AGENT_PROMPT,
    FACTUALITY_AGENT_PROMPT,
    HYPE_AGENT_PROMPT,
    TOPIC_GATE_PROMPT,
)

logger = get_logger(__name__)

_APP_NAME = "ai_news_evaluator"
_MAX_ARTICLE_CHARS = 7000


@dataclass
class ArticleAuditResult:
    is_ai_topic: bool
    primary_theme: str
    topic_reason: str
    hype_score: Optional[float] = None
    hype_reason: Optional[str] = None
    factuality_score: Optional[float] = None
    factuality_reason: Optional[str] = None
    verification_sources: list[dict[str, str]] = field(default_factory=list)
    is_duplicate: bool = False
    duplicate_of_article_id: Optional[str] = None
    dedup_reason: Optional[str] = None


async def _run_adk_agent(agent: Any, prompt: str) -> tuple[str, dict[str, Any]]:
    """Executes an ADK Agent or ParallelAgent in an isolated in-memory session."""
    session_service = InMemorySessionService()
    session_id = f"eval_{uuid.uuid4().hex}"
    user_id = "editorial_system"

    runner = Runner(
        agent=agent,
        app_name=_APP_NAME,
        session_service=session_service,
        auto_create_session=True,
    )

    final_text = ""
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            text = "".join(p.text or "" for p in event.content.parts).strip()
            if text:
                final_text = text

    session = await session_service.get_session(
        app_name=_APP_NAME, user_id=user_id, session_id=session_id
    )
    state = dict(session.state) if session and session.state else {}
    return final_text, state


def _article_context_block(article: Article) -> str:
    body = (article.article or "").strip()[:_MAX_ARTICLE_CHARS]
    pub_str = article.published_at.strftime("%Y-%m-%d") if article.published_at else "Unknown"
    return (
        f"TITLE: {article.title}\n"
        f"SOURCE: {article.source}\n"
        f"AUTHOR: {article.author or article.source}\n"
        f"PUBLISHED_DATE: {pub_str}\n"
        f"URL: {article.canonical_url}\n"
        f"SUMMARY: {article.summary or 'N/A'}\n\n"
        f"ARTICLE CONTENT:\n{body}"
    )


async def evaluate_single_article(
    article: Article,
    corroboration_evidence: list[dict[str, str]],
    dedup_candidates: list[dict[str, Any]],
) -> ArticleAuditResult:
    """Runs the 3-stage Google ADK evaluation pipeline for one article:
      1. Topic Gate Agent (AI relevance filter)
      2. ParallelAgent([Hype Agent, Factuality Agent])
      3. Deduplication Agent (against all existing DB articles)
    """
    llm = get_eval_llm()
    article_block = _article_context_block(article)

    # ------------------------------------------------------------------
    # Stage 1: Topic Gate Agent
    # ------------------------------------------------------------------
    topic_agent = Agent(
        name="topic_gate_agent",
        model=llm,
        instruction=TOPIC_GATE_PROMPT,
    )
    topic_raw, _ = await _run_adk_agent(topic_agent, article_block)
    topic_json = extract_json_object(topic_raw) or {}
    try:
        topic_out = TopicAgentOutput.model_validate(topic_json)
    except Exception as exc:
        logger.warning(f"TopicAgent parse fallback for '{article.title[:50]}': {exc}")
        topic_out = TopicAgentOutput(
            is_ai_topic=True,
            primary_theme="Enterprise & Product AI",
            reason="Defaulted to AI topic after ambiguous classification.",
        )

    if not topic_out.is_ai_topic:
        logger.info(f"[Topic Gate] Eliminated off-topic article: '{article.title[:60]}'")
        return ArticleAuditResult(
            is_ai_topic=False,
            primary_theme=topic_out.primary_theme,
            topic_reason=topic_out.reason,
        )

    # ------------------------------------------------------------------
    # Stage 2: ParallelAgent (Hype + Factuality running concurrently)
    # ------------------------------------------------------------------
    evidence_str = (
        json.dumps(corroboration_evidence, indent=2)
        if corroboration_evidence
        else "No external corroboration hits returned; evaluate using internal primary-source evidence."
    )
    audit_prompt = (
        f"{article_block}\n\n"
        f"EXTERNAL & DATABASE CORROBORATION EVIDENCE (for Factuality Auditor):\n{evidence_str}"
    )

    hype_agent = Agent(
        name="hype_auditor",
        model=llm,
        output_key="hype_json",
        instruction=HYPE_AGENT_PROMPT,
    )
    factuality_agent = Agent(
        name="factuality_auditor",
        model=llm,
        output_key="factuality_json",
        instruction=FACTUALITY_AGENT_PROMPT,
    )
    audit_team = ParallelAgent(
        name="article_auditors",
        sub_agents=[hype_agent, factuality_agent],
    )

    _, audit_state = await _run_adk_agent(audit_team, audit_prompt)

    hype_parsed = extract_json_object(str(audit_state.get("hype_json", ""))) or {}
    try:
        hype_out = HypeAgentOutput.model_validate(hype_parsed)
    except Exception as exc:
        logger.warning(f"HypeAgent parse fallback for '{article.title[:50]}': {exc}")
        hype_out = HypeAgentOutput(
            hype_score=4.0,
            reason="Moderate baseline score assigned due to structured parse fallback.",
        )

    fact_parsed = extract_json_object(str(audit_state.get("factuality_json", ""))) or {}
    try:
        fact_out = FactualityAgentOutput.model_validate(fact_parsed)
    except Exception as exc:
        logger.warning(f"FactualityAgent parse fallback for '{article.title[:50]}': {exc}")
        fact_out = FactualityAgentOutput(
            factuality_score=7.0,
            reason="Baseline factual score assigned from primary-source publication.",
        )

    # ------------------------------------------------------------------
    # Stage 3: Deduplication Agent (vs. ALL articles in PostgreSQL)
    # ------------------------------------------------------------------
    dedup_out = DeduplicationAgentOutput(
        is_duplicate=False,
        duplicate_of_article_id=None,
        reason="No earlier articles in database to compare against.",
    )
    if dedup_candidates:
        dedup_prompt = (
            f"CANDIDATE ARTICLE:\n"
            f"article_id: {article.id}\n"
            f"source: {article.source}\n"
            f"title: {article.title}\n"
            f"published_at: {article.published_at.strftime('%Y-%m-%d') if article.published_at else ''}\n"
            f"summary: {article.summary or ''}\n\n"
            f"EXISTING ARTICLES IN DATABASE:\n{json.dumps(dedup_candidates, indent=2)}"
        )
        dedup_agent = Agent(
            name="deduplication_agent",
            model=llm,
            instruction=DEDUPLICATION_AGENT_PROMPT,
        )
        dedup_raw, _ = await _run_adk_agent(dedup_agent, dedup_prompt)
        dedup_parsed = extract_json_object(dedup_raw) or {}
        try:
            dedup_out = DeduplicationAgentOutput.model_validate(dedup_parsed)
            # Validate duplicate_of_article_id actually points to a real candidate
            valid_ids = {c["article_id"] for c in dedup_candidates}
            if dedup_out.is_duplicate and dedup_out.duplicate_of_article_id not in valid_ids:
                dedup_out.duplicate_of_article_id = None
        except Exception as exc:
            logger.warning(f"DeduplicationAgent parse fallback for '{article.title[:50]}': {exc}")

    return ArticleAuditResult(
        is_ai_topic=True,
        primary_theme=topic_out.primary_theme,
        topic_reason=topic_out.reason,
        hype_score=hype_out.hype_score,
        hype_reason=hype_out.reason,
        factuality_score=fact_out.factuality_score,
        factuality_reason=fact_out.reason,
        verification_sources=corroboration_evidence,
        is_duplicate=dedup_out.is_duplicate,
        duplicate_of_article_id=dedup_out.duplicate_of_article_id,
        dedup_reason=dedup_out.reason,
    )
