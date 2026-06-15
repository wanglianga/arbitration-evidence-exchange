from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_roles
from app.routers.parties import check_case_access

router = APIRouter(prefix="/api/cases/{case_id}/reviews", tags=["证据审核"])


@router.post("", response_model=schemas.EvidenceReviewResponse, status_code=status.HTTP_201_CREATED)
def create_review(
    case_id: int,
    review_data: schemas.EvidenceReviewCreate,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    evidence = db.query(models.Evidence).filter(
        models.Evidence.id == review_data.evidence_id,
        models.Evidence.case_id == case_id
    ).first()
    if not evidence:
        raise HTTPException(status_code=404, detail="证据不存在")

    if evidence.status not in [models.EvidenceStatus.SUBMITTED, models.EvidenceStatus.REVIEWING]:
        raise HTTPException(status_code=400, detail="证据不在可审核状态")

    existing = db.query(models.EvidenceReview).filter(
        models.EvidenceReview.evidence_id == review_data.evidence_id,
        models.EvidenceReview.reviewer_id == current_user.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="您已对该证据进行过审核")

    evidence.status = models.EvidenceStatus.REVIEWING

    db_review = models.EvidenceReview(
        evidence_id=review_data.evidence_id,
        reviewer_id=current_user.id,
        status=review_data.status,
        format_ok=review_data.format_ok,
        desensitization_ok=review_data.desensitization_ok,
        page_number_ok=review_data.page_number_ok,
        comment=review_data.comment
    )
    db.add(db_review)

    if review_data.status == models.ReviewStatus.APPROVED:
        evidence.status = models.EvidenceStatus.APPROVED
        db_review.reviewed_at = datetime.utcnow()
    elif review_data.status == models.ReviewStatus.REJECTED:
        evidence.status = models.EvidenceStatus.REJECTED
        db_review.reviewed_at = datetime.utcnow()

    db.commit()
    db.refresh(db_review)
    return db_review


@router.get("", response_model=List[schemas.EvidenceReviewResponse])
def list_reviews(
    case_id: int,
    evidence_id: Optional[int] = None,
    status_filter: Optional[models.ReviewStatus] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    query = db.query(models.EvidenceReview).join(models.Evidence).filter(
        models.Evidence.case_id == case_id
    )
    if evidence_id:
        query = query.filter(models.EvidenceReview.evidence_id == evidence_id)
    if status_filter:
        query = query.filter(models.EvidenceReview.status == status_filter)

    return query.order_by(models.EvidenceReview.created_at.desc()).all()


@router.put("/{review_id}", response_model=schemas.EvidenceReviewResponse)
def update_review(
    case_id: int,
    review_id: int,
    review_data: schemas.EvidenceReviewUpdate,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    review = db.query(models.EvidenceReview).join(models.Evidence).filter(
        models.EvidenceReview.id == review_id,
        models.Evidence.case_id == case_id
    ).first()
    if not review:
        raise HTTPException(status_code=404, detail="审核记录不存在")

    if review.reviewer_id != current_user.id and current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="无权修改此审核记录")

    update_data = review_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(review, key, value)

    if review_data.status:
        evidence = db.query(models.Evidence).filter(models.Evidence.id == review.evidence_id).first()
        if evidence:
            if review_data.status == models.ReviewStatus.APPROVED:
                evidence.status = models.EvidenceStatus.APPROVED
                review.reviewed_at = datetime.utcnow()
            elif review_data.status == models.ReviewStatus.REJECTED:
                evidence.status = models.EvidenceStatus.REJECTED
                review.reviewed_at = datetime.utcnow()
            elif review_data.status == models.ReviewStatus.PENDING:
                evidence.status = models.EvidenceStatus.REVIEWING

    db.commit()
    db.refresh(review)
    return review
