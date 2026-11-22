from typing import Optional
import uuid
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from api.configs.database import get_db
from api.configs.logging import get_logger
from api.models.dtos.newsletter import (
    ApproveNewsletterRequest,
    DraftNewsletterRequest,
    NewsletterResponse,
    NewsletterSummaryDTO,
    SaveDraftRequest,
    SendNewsletterRequest,
    SendNewsletterResponse,
    SubscriberCreateRequest,
    SubscriberResponse,
)
from api.models.entities.newsletter import Subscriber
from api.services.newsletter_service import NewsletterService

logger = get_logger(__name__)
router = APIRouter(tags=["Newsletters & Subscribers"])


# ==============================================================================
# Subscribers Management
# ==============================================================================


@router.get("/subscribers", response_model=list[SubscriberResponse])
def list_subscribers(db: Session = Depends(get_db)):
    return (
        db.query(Subscriber)
        .filter(Subscriber.is_active.is_(True))
        .order_by(Subscriber.created_at.desc())
        .all()
    )


@router.post("/subscribers", response_model=SubscriberResponse)
def add_subscriber(req: SubscriberCreateRequest, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")

    existing = db.query(Subscriber).filter(Subscriber.email == email).first()
    if existing:
        existing.is_active = True
        if req.name:
            existing.name = req.name.strip()
        db.commit()
        db.refresh(existing)
        return existing

    sub = Subscriber(email=email, name=(req.name or "").strip() or None, is_active=True)
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@router.delete("/subscribers/{subscriber_id}")
def remove_subscriber(subscriber_id: uuid.UUID, db: Session = Depends(get_db)):
    sub = db.query(Subscriber).filter(Subscriber.id == subscriber_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscriber not found.")
    db.delete(sub)
    db.commit()
    return {"status": "deleted"}


# ==============================================================================
# Newsletter Editions (Draft -> Approve -> Send)
# ==============================================================================


@router.post("/draft", response_model=NewsletterResponse)
async def create_newsletter_draft(
    req: DraftNewsletterRequest, db: Session = Depends(get_db)
):
    """Applies HitL curation choices and synthesizes a Structured JSON draft via Google ADK."""
    logger.info(f"HTTP POST /newsletters/draft called ({len(req.selected_article_ids)} articles).")
    service = NewsletterService(db=db)
    try:
        return await service.draft_newsletter(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("", response_model=list[NewsletterSummaryDTO])
def list_newsletters(db: Session = Depends(get_db)):
    service = NewsletterService(db=db)
    return service.list_newsletters()


@router.get("/{newsletter_id}", response_model=NewsletterResponse)
def get_newsletter(newsletter_id: uuid.UUID, db: Session = Depends(get_db)):
    service = NewsletterService(db=db)
    nl = service.get_newsletter(newsletter_id)
    if not nl:
        raise HTTPException(status_code=404, detail="Newsletter edition not found.")
    return nl


@router.patch("/{newsletter_id}", response_model=NewsletterResponse)
def save_newsletter_draft(
    newsletter_id: uuid.UUID,
    req: SaveDraftRequest,
    db: Session = Depends(get_db),
):
    """Saves inline human edits to a draft without approving it."""
    service = NewsletterService(db=db)
    try:
        return service.save_newsletter_draft(newsletter_id, req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/{newsletter_id}/approve", response_model=NewsletterResponse)
def approve_newsletter(
    newsletter_id: uuid.UUID,
    req: Optional[ApproveNewsletterRequest] = Body(default=None),
    db: Session = Depends(get_db),
):
    """Explicitly approves a newsletter edition, records Section 5 edit metrics, and updates reputation."""
    service = NewsletterService(db=db)
    try:
        return service.approve_newsletter(newsletter_id, req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{newsletter_id}/send", response_model=SendNewsletterResponse)
def send_newsletter(
    newsletter_id: uuid.UUID,
    req: SendNewsletterRequest,
    db: Session = Depends(get_db),
):
    """Dispatches newsletter HTML email via Mailpit SMTP to subscribers or a single test inbox."""
    service = NewsletterService(db=db)
    try:
        return service.send_newsletter(newsletter_id, test_email=req.test_email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"Email delivery failed for newsletter {newsletter_id}: {exc}")
        raise HTTPException(status_code=502, detail=f"Email delivery error: {exc}")
