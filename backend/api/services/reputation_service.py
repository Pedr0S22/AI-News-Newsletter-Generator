from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from api.configs.config import settings
from api.configs.logging import get_logger
from api.models.entities.source_reputation import SourceReputation

logger = get_logger(__name__)

# Human-in-the-Loop (HitL) Reputation Modifiers
DELTA_ACCEPT_UNTOUCHED = 0.05
DELTA_ACCEPT_EDITED = 0.01
DELTA_REJECT_FROM_TOP_N = -0.08
DELTA_PROMOTE_RESCUE = 0.05


class ReputationService:
    """Manages domain-level source reputation and computes weighted article rankings."""

    def __init__(self, db: Session):
        self.db = db

    def get_or_create_source(self, source_name: str) -> SourceReputation:
        rep = (
            self.db.query(SourceReputation)
            .filter(SourceReputation.source_name == source_name)
            .first()
        )
        if not rep:
            rep = SourceReputation(
                source_name=source_name,
                reputation_score=settings.REPUTATION_DEFAULT,
                accepted_count=0,
                rejected_count=0,
                edited_count=0,
                promoted_count=0,
                total_evaluated=0,
                history=[
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "event": "initialized",
                        "delta": 0.0,
                        "new_score": settings.REPUTATION_DEFAULT,
                        "article_title": None,
                    }
                ],
            )
            self.db.add(rep)
            self.db.flush()
        return rep

    @staticmethod
    def compute_ranking(
        factuality_score: float,
        hype_score: float,
        reputation_score: float,
    ) -> tuple[float, float, float]:
        """Computes (groundedness, weighted_subscore, final_ranking_score).

        Formula:
            groundedness = 11 - hype_score  (maps 1..10 lower-is-better -> 10..1 higher-is-better)
            weighted_subscore = w_fact * factuality + w_hype * groundedness
            final_ranking_score = weighted_subscore * reputation_score
        """
        clamped_fact = max(1.0, min(10.0, float(factuality_score)))
        clamped_hype = max(1.0, min(10.0, float(hype_score)))
        groundedness = round(11.0 - clamped_hype, 2)

        w_sum = settings.WEIGHT_FACTUALITY + settings.WEIGHT_HYPE
        w_fact = settings.WEIGHT_FACTUALITY / w_sum if w_sum > 0 else 0.5
        w_hype = settings.WEIGHT_HYPE / w_sum if w_sum > 0 else 0.5

        weighted_subscore = round((w_fact * clamped_fact) + (w_hype * groundedness), 3)
        final_ranking = round(weighted_subscore * float(reputation_score), 3)
        return groundedness, weighted_subscore, final_ranking

    def record_evaluation(self, source_name: str) -> SourceReputation:
        rep = self.get_or_create_source(source_name)
        rep.total_evaluated = (rep.total_evaluated or 0) + 1
        return rep

    def apply_hitl_feedback(
        self,
        source_name: str,
        event: str,
        article_title: Optional[str] = None,
    ) -> SourceReputation:
        """Adjusts source reputation based on a Human-in-the-Loop editorial decision.

        Supported events:
        - 'accepted_untouched': +0.05
        - 'accepted_edited': +0.01
        - 'rejected_top_n': -0.08
        - 'promoted': +0.05
        """
        delta_map = {
            "accepted_untouched": DELTA_ACCEPT_UNTOUCHED,
            "accepted_edited": DELTA_ACCEPT_EDITED,
            "rejected_top_n": DELTA_REJECT_FROM_TOP_N,
            "promoted": DELTA_PROMOTE_RESCUE,
        }
        delta = delta_map.get(event, 0.0)
        rep = self.get_or_create_source(source_name)

        old_score = rep.reputation_score
        new_score = round(
            max(settings.REPUTATION_MIN, min(settings.REPUTATION_MAX, old_score + delta)),
            4,
        )
        rep.reputation_score = new_score

        if event == "accepted_untouched":
            rep.accepted_count = (rep.accepted_count or 0) + 1
        elif event == "accepted_edited":
            rep.accepted_count = (rep.accepted_count or 0) + 1
            rep.edited_count = (rep.edited_count or 0) + 1
        elif event == "rejected_top_n":
            rep.rejected_count = (rep.rejected_count or 0) + 1
        elif event == "promoted":
            rep.promoted_count = (rep.promoted_count or 0) + 1

        history = list(rep.history or [])
        history.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": event,
                "delta": delta,
                "new_score": new_score,
                "article_title": (article_title or "")[:140] or None,
            }
        )
        rep.history = history
        rep.updated_at = datetime.now(timezone.utc)

        logger.info(
            f"Reputation updated for '{source_name}' ({event}): {old_score:.3f} -> {new_score:.3f}"
        )
        return rep
