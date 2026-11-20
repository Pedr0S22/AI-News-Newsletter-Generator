"""Unit tests for Phase 2: IAedu stream parsing, ranking math, reputation HitL, and newsletter rendering."""
from api.models.dtos.newsletter import NewsletterBlurbDTO, NewsletterStructuredContent
from api.services.agents.iaedu_llm import extract_json_object, parse_iaedu_stream_text
from api.services.email_service import EmailService
from api.services.reputation_service import ReputationService


def test_parse_iaedu_stream_prefers_final_message():
    raw = (
        '{"run_id": "1", "type": "start", "content": "Processing"}\n\n'
        '{"run_id": "1", "type": "token", "content": "{\\"ok\\":"}\n\n'
        '{"run_id": "1", "type": "token", "content": "true}"}\n\n'
        '{"run_id": "1", "type": "message", "content": {"type": "ai", "content": "{\\"ok\\": true, \\"model\\": \\"GPT-5.5\\"}"}}\n\n'
    )
    parsed_text = parse_iaedu_stream_text(raw)
    obj = extract_json_object(parsed_text)
    assert obj == {"ok": True, "model": "GPT-5.5"}


def test_parse_iaedu_stream_falls_back_to_tokens():
    raw = (
        '{"run_id": "2", "type": "token", "content": "{\\"hype_score\\": "}\n\n'
        '{"run_id": "2", "type": "token", "content": "2.0, \\"reason\\": \\"Grounded\\"}"}\n\n'
    )
    obj = extract_json_object(parse_iaedu_stream_text(raw))
    assert obj == {"hype_score": 2.0, "reason": "Grounded"}


def test_extract_json_handles_markdown_fences():
    fenced = 'Here is the JSON:\n```json\n{"is_ai_topic": true, "primary_theme": "AI Safety"}\n```'
    assert extract_json_object(fenced) == {"is_ai_topic": True, "primary_theme": "AI Safety"}


def test_ranking_formula_50_50_with_hype_inversion():
    # Factuality = 9.0, Hype = 2.0 -> Groundedness = 11 - 2 = 9.0
    # Weighted avg (50/50) = 9.0; Reputation = 1.1 -> Ranking = 9.9
    groundedness, weighted, final_rank = ReputationService.compute_ranking(
        factuality_score=9.0,
        hype_score=2.0,
        reputation_score=1.1,
    )
    assert groundedness == 9.0
    assert weighted == 9.0
    assert final_rank == 9.9

    # High hype (9.0) -> Groundedness = 2.0; Factuality = 4.0 -> Weighted = 3.0; Rep = 0.5 -> 1.5
    g2, w2, r2 = ReputationService.compute_ranking(
        factuality_score=4.0,
        hype_score=9.0,
        reputation_score=0.5,
    )
    assert g2 == 2.0
    assert w2 == 3.0
    assert r2 == 1.5


def test_newsletter_rendering_contains_no_internal_scores():
    content = NewsletterStructuredContent(
        edition_title="AI Pulse Digest",
        subject="OpenAI Scales Storage and Anthropic Donates Agent Skills",
        intro="Two major engineering milestones headline this week's AI briefing.",
        blurbs=[
            NewsletterBlurbDTO(
                article_id="00000000-0000-0000-0000-000000000001",
                rank_order=1,
                theme="AI Hardware & Infrastructure",
                headline="OpenAI Scales Habitat Storage Platform",
                body="OpenAI detailed how it redesigned Habitat on Cosmos DB for 1B users.",
                source_name="OpenAI News",
                source_url="https://openai.com/index/habitat",
            )
        ],
        outro="Thanks for reading AI Pulse Digest.",
    )

    svc = EmailService()
    html = svc.render_html(content)
    md = svc.render_markdown(content)

    assert "OpenAI Scales Habitat Storage Platform" in html
    assert "https://openai.com/index/habitat" in html
    assert "AI Pulse Digest" in md
    for forbidden in ("hype_score", "factuality_score", "reputation_multiplier", "final_ranking_score"):
        assert forbidden not in html.lower()
        assert forbidden not in md.lower()
