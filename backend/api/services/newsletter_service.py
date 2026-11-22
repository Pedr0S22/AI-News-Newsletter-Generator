import asyncio
import difflib
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy.orm import Session

from api.configs.config import settings
from api.configs.logging import get_logger
from api.models.dtos.evaluation import (
    AnalyticsResponse,
    EvaluatedArticleDTO,
    EvaluationRunResponse,
    RankingsResponse,
    SourceReputationDTO,
    VerificationSourceDTO,
)
from api.models.dtos.newsletter import (
    ApproveNewsletterRequest,
    DraftNewsletterRequest,
    NewsletterResponse,
    NewsletterStructuredContent,
    NewsletterSummaryDTO,
    SendNewsletterResponse,
)
from api.models.entities.article import Article
from api.models.entities.article_evaluation import ArticleEvaluation
from api.models.entities.newsletter import Newsletter, NewsletterItem, Subscriber
from api.models.entities.source_reputation import SourceReputation
from api.services.agents.evaluation_pipeline import (
    ArticleAuditResult,
    evaluate_single_article,
)
from api.services.agents.synthesis_pipeline import synthesize_newsletter_draft
from api.services.agents.verification_tools import (
    gather_corroboration_evidence,
    select_dedup_candidates,
)
from api.services.email_service import EmailService
from api.services.reputation_service import ReputationService

logger = get_logger(__name__)


class NewsletterService:
    """Coordinates PostgreSQL persistence, Google ADK agents, Reputation HitL, and Email delivery."""

    def __init__(self, db: Session):
        self.db = db
        self.reputation_service = ReputationService(db)
        self.email_service = EmailService()

    # ==========================================================================
    # 1. Multi-Agent Evaluation Pipeline (Auto-triggered after Ingestion)
    # ==========================================================================

    async def evaluate_unevaluated_articles(self) -> EvaluationRunResponse:
        """Evaluates all articles in PostgreSQL that do not yet have an ArticleEvaluation."""
        all_articles = (
            self.db.query(Article)
            .order_by(Article.published_at.asc(), Article.created_at.asc())
            .all()
        )
        existing_eval_ids = {
            row[0] for row in self.db.query(ArticleEvaluation.article_id).all()
        }
        pending_articles = [a for a in all_articles if a.id not in existing_eval_ids]

        if not pending_articles:
            logger.info("No unevaluated articles found. Skipping ADK evaluation.")
            return EvaluationRunResponse(
                status="up_to_date",
                evaluated_count=0,
                ranked_count=0,
                eliminated_topic_count=0,
                eliminated_duplicate_count=0,
                failed_count=0,
            )

        provider = (settings.EVAL_LLM_PROVIDER or "ollama").strip().lower()
        effective_concurrency = (
            1 if provider == "ollama" else max(1, settings.AGENT_MAX_CONCURRENCY)
        )
        logger.info(
            f"Running ADK Multi-Agent Evaluation on {len(pending_articles)} unevaluated articles "
            f"(provider={provider}, concurrency={effective_concurrency})..."
        )

        # Pre-compute deduplication candidate snapshots on the main DB thread
        # Each article compares against all earlier/other articles in DB
        dedup_map: dict[uuid.UUID, list[dict[str, Any]]] = {}
        seen_earlier: list[Article] = [a for a in all_articles if a.id in existing_eval_ids]
        for art in pending_articles:
            dedup_map[art.id] = select_dedup_candidates(art, seen_earlier)
            seen_earlier.append(art)

        semaphore = asyncio.Semaphore(effective_concurrency)
        total_pending = len(pending_articles)

        async def _worker(
            idx: int, art: Article
        ) -> tuple[Article, Optional[ArticleAuditResult], Optional[Exception]]:
            async with semaphore:
                try:
                    evidence = await asyncio.to_thread(
                        gather_corroboration_evidence, art, all_articles
                    )
                    audit = await evaluate_single_article(
                        article=art,
                        corroboration_evidence=evidence,
                        dedup_candidates=dedup_map.get(art.id, []),
                        progress_label=f"{idx}/{total_pending}",
                    )
                    return art, audit, None
                except Exception as exc:
                    logger.error(f"Evaluation failed for article '{art.title[:60]}': {exc}")
                    return art, None, exc

        results = await asyncio.gather(
            *(_worker(i, a) for i, a in enumerate(pending_articles, start=1))
        )

        ranked_count = 0
        eliminated_topic_count = 0
        eliminated_duplicate_count = 0
        failed_count = 0

        for art, audit, exc in results:
            if exc or audit is None:
                failed_count += 1
                continue

            rep = self.reputation_service.record_evaluation(art.source)

            if not audit.is_ai_topic:
                status = "eliminated_topic"
                groundedness = None
                weighted_sub = 0.0
                final_rank = 0.0
                eliminated_topic_count += 1
            else:
                groundedness, weighted_sub, final_rank = ReputationService.compute_ranking(
                    factuality_score=audit.factuality_score or 5.0,
                    hype_score=audit.hype_score or 5.0,
                    reputation_score=rep.reputation_score,
                )
                if audit.is_duplicate:
                    status = "eliminated_duplicate"
                    eliminated_duplicate_count += 1
                else:
                    status = "ranked"
                    ranked_count += 1

            dup_uuid: Optional[uuid.UUID] = None
            if audit.duplicate_of_article_id:
                try:
                    dup_uuid = uuid.UUID(str(audit.duplicate_of_article_id))
                except ValueError:
                    dup_uuid = None

            eval_row = ArticleEvaluation(
                article_id=art.id,
                is_ai_topic=audit.is_ai_topic,
                primary_theme=audit.primary_theme,
                topic_reason=audit.topic_reason,
                hype_score=audit.hype_score,
                groundedness_score=groundedness,
                hype_reason=audit.hype_reason,
                factuality_score=audit.factuality_score,
                factuality_reason=audit.factuality_reason,
                verification_sources=audit.verification_sources,
                is_duplicate=audit.is_duplicate,
                duplicate_of_article_id=dup_uuid,
                dedup_reason=audit.dedup_reason,
                weighted_subscore=weighted_sub,
                reputation_snapshot=rep.reputation_score,
                final_ranking_score=final_rank,
                status=status,
            )
            self.db.add(eval_row)
            logger.info(
                f"[Eval Saved] '{art.title[:55]}' | Status: {status} | "
                f"Ranking: {final_rank:.2f} (Rep: {rep.reputation_score:.2f}x)"
            )

        self.db.commit()
        evaluated_total = ranked_count + eliminated_topic_count + eliminated_duplicate_count
        logger.info(
            f"Evaluation complete: {evaluated_total} evaluated "
            f"(ranked={ranked_count}, off_topic={eliminated_topic_count}, "
            f"duplicates={eliminated_duplicate_count}, failed={failed_count})."
        )
        return EvaluationRunResponse(
            status="success",
            evaluated_count=evaluated_total,
            ranked_count=ranked_count,
            eliminated_topic_count=eliminated_topic_count,
            eliminated_duplicate_count=eliminated_duplicate_count,
            failed_count=failed_count,
        )

    # ==========================================================================
    # 2. Live Rankings Retrieval (Excludes Already-Published Articles)
    # ==========================================================================

    def get_rankings(self, top_n: Optional[int] = None) -> RankingsResponse:
        desired_n = top_n or settings.DEFAULT_TOP_N
        desired_n = max(1, min(settings.MAX_TOP_N, desired_n))

        # Pre-load live reputations so rankings reflect latest HitL updates immediately
        rep_map = {
            r.source_name: r.reputation_score
            for r in self.db.query(SourceReputation).all()
        }

        total_articles = self.db.query(Article).count()
        rows = (
            self.db.query(Article, ArticleEvaluation)
            .join(ArticleEvaluation, Article.id == ArticleEvaluation.article_id)
            .all()
        )
        unevaluated_count = max(0, total_articles - len(rows))

        eligible: list[EvaluatedArticleDTO] = []
        rejected_pool: list[EvaluatedArticleDTO] = []
        eliminated: list[EvaluatedArticleDTO] = []

        for art, ev in rows:
            # Exclude articles already shipped in a sent newsletter from Top-N recommendations
            if ev.status == "published":
                continue

            live_rep = rep_map.get(art.source, settings.REPUTATION_DEFAULT)
            if ev.is_ai_topic and ev.factuality_score is not None and ev.hype_score is not None:
                groundedness, weighted_sub, live_rank = ReputationService.compute_ranking(
                    factuality_score=ev.factuality_score,
                    hype_score=ev.hype_score,
                    reputation_score=live_rep,
                )
            else:
                groundedness = ev.groundedness_score
                weighted_sub = ev.weighted_subscore
                live_rank = ev.final_ranking_score

            dto = EvaluatedArticleDTO(
                article_id=art.id,
                source=art.source,
                canonical_url=art.canonical_url,
                original_url=art.original_url,
                title=art.title,
                summary=art.summary,
                author=art.author,
                published_at=art.published_at,
                is_ai_topic=ev.is_ai_topic,
                primary_theme=ev.primary_theme,
                topic_reason=ev.topic_reason,
                hype_score=ev.hype_score,
                groundedness_score=groundedness,
                hype_reason=ev.hype_reason,
                factuality_score=ev.factuality_score,
                factuality_reason=ev.factuality_reason,
                verification_sources=[
                    VerificationSourceDTO.model_validate(s)
                    for s in (ev.verification_sources or [])
                    if isinstance(s, dict)
                ],
                is_duplicate=ev.is_duplicate,
                duplicate_of_article_id=ev.duplicate_of_article_id,
                dedup_reason=ev.dedup_reason,
                weighted_subscore=weighted_sub,
                reputation_multiplier=round(live_rep, 3),
                final_ranking_score=live_rank,
                status=ev.status,
            )

            if ev.status in ("eliminated_topic", "eliminated_duplicate"):
                eliminated.append(dto)
            elif ev.status == "human_rejected":
                rejected_pool.append(dto)
            else:
                eligible.append(dto)

        eligible.sort(key=lambda x: (x.final_ranking_score, x.published_at), reverse=True)
        rejected_pool.sort(key=lambda x: (x.final_ranking_score, x.published_at), reverse=True)
        eliminated.sort(key=lambda x: x.published_at, reverse=True)

        recommended = eligible[:desired_n]
        for idx, item in enumerate(recommended, start=1):
            item.recommended_rank = idx

        candidate_pool = eligible[desired_n:] + rejected_pool

        return RankingsResponse(
            top_n=desired_n,
            recommended=recommended,
            candidate_pool=candidate_pool,
            eliminated=eliminated,
            unevaluated_count=unevaluated_count,
        )

    # ==========================================================================
    # 3. HitL Curation + ADK Synthesis & Reflection Draft Generation
    # ==========================================================================

    async def draft_newsletter(self, req: DraftNewsletterRequest) -> NewsletterResponse:
        selected_ids = req.selected_article_ids
        articles = (
            self.db.query(Article)
            .filter(Article.id.in_(selected_ids))
            .all()
        )
        article_by_id = {a.id: a for a in articles}
        ordered_articles = [article_by_id[aid] for aid in selected_ids if aid in article_by_id]
        if not ordered_articles:
            raise ValueError("None of the selected article IDs were found in the database.")

        evals = (
            self.db.query(ArticleEvaluation)
            .filter(ArticleEvaluation.article_id.in_(list(selected_ids) + list(req.rejected_article_ids)))
            .all()
        )
        eval_by_id = {e.article_id: e for e in evals}

        suggested_set = set(req.suggested_top_n_ids)
        selected_set = set(selected_ids)

        # Apply HitL Reputation Updates for Rejections and Promotions
        if req.rejected_article_ids:
            rej_articles = (
                self.db.query(Article)
                .filter(Article.id.in_(req.rejected_article_ids))
                .all()
            )
            for r_art in rej_articles:
                ev = eval_by_id.get(r_art.id)
                if ev:
                    ev.status = "human_rejected"
                self.reputation_service.apply_hitl_feedback(
                    r_art.source, "rejected_top_n", r_art.title
                )

        for art in ordered_articles:
            ev = eval_by_id.get(art.id)
            if ev:
                ev.status = "human_approved"
            if suggested_set and art.id not in suggested_set:
                self.reputation_service.apply_hitl_feedback(
                    art.source, "promoted", art.title
                )

        # Compute Proposal Section 5 Curation Metrics
        kept_from_suggested = [aid for aid in selected_ids if aid in suggested_set]
        retention_rate = (
            round(len(kept_from_suggested) / len(suggested_set), 4)
            if suggested_set
            else 1.0
        )
        suggested_kept_order = [aid for aid in req.suggested_top_n_ids if aid in selected_set]
        reordered = kept_from_suggested != suggested_kept_order

        # Build clean input for ADK Writer + Reflection Loop (NO internal scores passed!)
        curated_payload = []
        for art in ordered_articles:
            ev = eval_by_id.get(art.id)
            curated_payload.append(
                {
                    "article_id": str(art.id),
                    "theme": (ev.primary_theme if ev and ev.primary_theme else "AI News"),
                    "title": art.title,
                    "source_name": art.source,
                    "source_url": art.canonical_url or art.original_url or "",
                    "author": art.author or art.source,
                    "published_at": art.published_at.strftime("%Y-%m-%d") if art.published_at else "",
                    "summary": art.summary or "",
                    "article_text": art.article or "",
                }
            )

        edition_title = (req.edition_title or settings.NEWSLETTER_DEFAULT_TITLE).strip()
        structured = await synthesize_newsletter_draft(
            curated_articles=curated_payload,
            edition_title=edition_title,
        )

        full_markdown = self.email_service.render_markdown(structured)
        full_html = self.email_service.render_html(structured)

        nl = Newsletter(
            edition_title=structured.edition_title,
            subject=structured.subject,
            structured_content=structured.model_dump(),
            full_markdown=full_markdown,
            full_html=full_html,
            status="draft",
            selected_count=len(structured.blurbs),
            hitl_metrics={
                "suggested_top_n_ids": [str(i) for i in req.suggested_top_n_ids],
                "final_selected_ids": [str(i) for i in selected_ids],
                "rejected_ids": [str(i) for i in req.rejected_article_ids],
                "top_n_retention_rate": retention_rate,
                "reordered": reordered,
                "avg_edit_ratio": 0.0,
                "unedited_items_ratio": 1.0,
            },
        )
        self.db.add(nl)
        self.db.flush()

        for blurb in structured.blurbs:
            try:
                art_uuid = uuid.UUID(blurb.article_id)
            except ValueError:
                continue
            item = NewsletterItem(
                newsletter_id=nl.id,
                article_id=art_uuid,
                rank_order=blurb.rank_order,
                theme=blurb.theme,
                headline=blurb.headline,
                source_name=blurb.source_name,
                source_url=blurb.source_url,
                ai_generated_body=blurb.body,
                human_approved_body=blurb.body,
                was_edited=False,
                edit_ratio=0.0,
            )
            self.db.add(item)

        self.db.commit()
        self.db.refresh(nl)
        return NewsletterResponse.model_validate(nl)

    # ==========================================================================
    # 4. Human Inline Edit, Approval & Section 5 Metrics
    # ==========================================================================

    def approve_newsletter(
        self, newsletter_id: uuid.UUID, req: ApproveNewsletterRequest
    ) -> NewsletterResponse:
        nl = self.db.query(Newsletter).filter(Newsletter.id == newsletter_id).first()
        if not nl:
            raise ValueError("Newsletter edition not found.")

        was_already_approved = nl.status in ("approved", "sent")
        structured = req.structured_content
        blurb_by_article_id = {b.article_id: b for b in structured.blurbs}

        edit_ratios: list[float] = []
        unedited_count = 0

        for item in nl.items:
            updated_blurb = blurb_by_article_id.get(str(item.article_id))
            if updated_blurb:
                item.headline = updated_blurb.headline.strip()
                item.theme = updated_blurb.theme.strip()
                item.human_approved_body = updated_blurb.body.strip()

                similarity = difflib.SequenceMatcher(
                    None,
                    (item.ai_generated_body or "").strip(),
                    item.human_approved_body,
                ).ratio()
                ratio = round(1.0 - similarity, 4)
                item.edit_ratio = ratio
                item.was_edited = ratio > 0.02
                edit_ratios.append(ratio)
                if not item.was_edited:
                    unedited_count += 1

                # Apply reputation acceptance feedback only once upon initial approval
                if not was_already_approved:
                    event_name = "accepted_edited" if item.was_edited else "accepted_untouched"
                    self.reputation_service.apply_hitl_feedback(
                        item.source_name, event_name, item.headline
                    )

        nl.edition_title = structured.edition_title.strip()
        nl.subject = structured.subject.strip()
        nl.structured_content = structured.model_dump()
        nl.full_markdown = self.email_service.render_markdown(structured)
        nl.full_html = self.email_service.render_html(structured)
        if nl.status != "sent":
            nl.status = "approved"
        nl.approved_at = datetime.now(timezone.utc)

        metrics = dict(nl.hitl_metrics or {})
        if edit_ratios:
            metrics["avg_edit_ratio"] = round(sum(edit_ratios) / len(edit_ratios), 4)
            metrics["unedited_items_ratio"] = round(unedited_count / len(edit_ratios), 4)
        nl.hitl_metrics = metrics

        self.db.commit()
        self.db.refresh(nl)
        return NewsletterResponse.model_validate(nl)

    # ==========================================================================
    # 5. Mailpit SMTP Dispatch & Article Publication Retirement
    # ==========================================================================

    def send_newsletter(
        self, newsletter_id: uuid.UUID, test_email: Optional[str] = None
    ) -> SendNewsletterResponse:
        nl = self.db.query(Newsletter).filter(Newsletter.id == newsletter_id).first()
        if not nl:
            raise ValueError("Newsletter edition not found.")

        if test_email and test_email.strip():
            sent_to = self.email_service.send_email(
                recipients=[test_email.strip()],
                subject=f"[TEST] {nl.subject}",
                plain_markdown=nl.full_markdown,
                html_body=nl.full_html,
            )
            return SendNewsletterResponse(
                status="sent_test",
                recipients_count=len(sent_to),
                recipients=sent_to,
                is_test=True,
            )

        subscribers = (
            self.db.query(Subscriber).filter(Subscriber.is_active.is_(True)).all()
        )
        if not subscribers:
            raise ValueError(
                "No active subscribers found. Add at least one subscriber or send a test email."
            )

        recipients = [s.email for s in subscribers]
        sent_to = self.email_service.send_email(
            recipients=recipients,
            subject=nl.subject,
            plain_markdown=nl.full_markdown,
            html_body=nl.full_html,
        )

        # Mark newsletter as sent & retire included articles from future Top-N recommendations
        nl.status = "sent"
        nl.sent_at = datetime.now(timezone.utc)
        if not nl.approved_at:
            nl.approved_at = nl.sent_at

        included_article_ids = [item.article_id for item in nl.items]
        if included_article_ids:
            (
                self.db.query(ArticleEvaluation)
                .filter(ArticleEvaluation.article_id.in_(included_article_ids))
                .update({ArticleEvaluation.status: "published"}, synchronize_session=False)
            )

        self.db.commit()
        return SendNewsletterResponse(
            status="sent",
            recipients_count=len(sent_to),
            recipients=sent_to,
            is_test=False,
        )

    # ==========================================================================
    # 6. Listings & Proposal Section 5 Analytics
    # ==========================================================================

    def list_newsletters(self) -> list[NewsletterSummaryDTO]:
        rows = (
            self.db.query(Newsletter)
            .order_by(Newsletter.created_at.desc())
            .limit(50)
            .all()
        )
        return [NewsletterSummaryDTO.model_validate(r) for r in rows]

    def get_newsletter(self, newsletter_id: uuid.UUID) -> Optional[NewsletterResponse]:
        nl = self.db.query(Newsletter).filter(Newsletter.id == newsletter_id).first()
        return NewsletterResponse.model_validate(nl) if nl else None

    def get_analytics(self) -> AnalyticsResponse:
        reputations = (
            self.db.query(SourceReputation)
            .order_by(SourceReputation.reputation_score.desc())
            .all()
        )
        total_articles = self.db.query(Article).count()
        total_evaluated = self.db.query(ArticleEvaluation).count()
        total_eliminated = (
            self.db.query(ArticleEvaluation)
            .filter(
                ArticleEvaluation.status.in_(["eliminated_topic", "eliminated_duplicate"])
            )
            .count()
        )
        newsletters = self.db.query(Newsletter).all()
        editions_drafted = len(newsletters)
        editions_sent = sum(1 for n in newsletters if n.status == "sent")
        active_subscribers = (
            self.db.query(Subscriber).filter(Subscriber.is_active.is_(True)).count()
        )

        retention_vals = [
            float(n.hitl_metrics["top_n_retention_rate"])
            for n in newsletters
            if isinstance(n.hitl_metrics, dict)
            and "top_n_retention_rate" in n.hitl_metrics
        ]
        unedited_vals = [
            float(n.hitl_metrics["unedited_items_ratio"])
            for n in newsletters
            if n.status in ("approved", "sent")
            and isinstance(n.hitl_metrics, dict)
            and "unedited_items_ratio" in n.hitl_metrics
        ]
        edit_vals = [
            float(n.hitl_metrics["avg_edit_ratio"])
            for n in newsletters
            if n.status in ("approved", "sent")
            and isinstance(n.hitl_metrics, dict)
            and "avg_edit_ratio" in n.hitl_metrics
        ]

        return AnalyticsResponse(
            reputations=[SourceReputationDTO.model_validate(r) for r in reputations],
            total_articles=total_articles,
            total_evaluated=total_evaluated,
            total_eliminated=total_eliminated,
            editions_drafted=editions_drafted,
            editions_sent=editions_sent,
            active_subscribers=active_subscribers,
            avg_top_n_retention_rate=(
                round(sum(retention_vals) / len(retention_vals), 4)
                if retention_vals
                else None
            ),
            unedited_approval_rate=(
                round(sum(unedited_vals) / len(unedited_vals), 4)
                if unedited_vals
                else None
            ),
            avg_edit_ratio=(
                round(sum(edit_vals) / len(edit_vals), 4) if edit_vals else None
            ),
        )
