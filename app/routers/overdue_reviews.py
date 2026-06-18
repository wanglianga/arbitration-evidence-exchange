from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_roles
from app.routers.parties import check_case_access

router = APIRouter(prefix="/api/cases/{case_id}/overdue-reviews", tags=["超期证据审核"])


@router.post("", response_model=schemas.OverdueReviewResponse, status_code=status.HTTP_201_CREATED)
def create_overdue_review(
    case_id: int,
    review_data: schemas.OverdueReviewCreate,
    current_user: models.User = Depends(require_roles(models.UserRole.CLAIMANT, models.UserRole.RESPONDENT, models.UserRole.AGENT)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    evidence = db.query(models.Evidence).filter(
        models.Evidence.id == review_data.evidence_id,
        models.Evidence.case_id == case_id
    ).first()
    if not evidence:
        raise HTTPException(status_code=404, detail="证据不存在")

    if not evidence.is_overdue:
        raise HTTPException(status_code=400, detail="该证据未超期，无需进行超期审核")

    if evidence.submitter_id != current_user.id and current_user.role not in [models.UserRole.ADMIN, models.UserRole.SECRETARY]:
        raise HTTPException(status_code=403, detail="只能为自己提交的超期证据创建审核申请")

    existing = db.query(models.OverdueEvidenceReview).filter(
        models.OverdueEvidenceReview.evidence_id == review_data.evidence_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="该证据已存在超期审核记录")

    db_review = models.OverdueEvidenceReview(
        evidence_id=review_data.evidence_id,
        late_reason=review_data.late_reason,
        status=models.OverdueReviewStatus.PENDING
    )
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    return db_review


@router.get("", response_model=List[schemas.OverdueReviewResponse])
def list_overdue_reviews(
    case_id: int,
    status_filter: Optional[models.OverdueReviewStatus] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    query = db.query(models.OverdueEvidenceReview).join(
        models.Evidence, models.OverdueEvidenceReview.evidence_id == models.Evidence.id
    ).filter(models.Evidence.case_id == case_id)

    if status_filter:
        query = query.filter(models.OverdueEvidenceReview.status == status_filter)

    if current_user.role in [models.UserRole.CLAIMANT, models.UserRole.RESPONDENT, models.UserRole.AGENT]:
        query = query.filter(models.Evidence.submitter_id == current_user.id)

    return query.order_by(models.OverdueEvidenceReview.created_at.desc()).all()


@router.get("/{review_id}", response_model=schemas.OverdueReviewResponse)
def get_overdue_review(
    case_id: int,
    review_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    review = db.query(models.OverdueEvidenceReview).join(
        models.Evidence, models.OverdueEvidenceReview.evidence_id == models.Evidence.id
    ).filter(
        models.OverdueEvidenceReview.id == review_id,
        models.Evidence.case_id == case_id
    ).first()
    if not review:
        raise HTTPException(status_code=404, detail="超期审核记录不存在")

    if current_user.role in [models.UserRole.CLAIMANT, models.UserRole.RESPONDENT, models.UserRole.AGENT]:
        evidence = db.query(models.Evidence).filter(models.Evidence.id == review.evidence_id).first()
        if evidence and evidence.submitter_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权查看此审核记录")

    return review


@router.put("/{review_id}/secretary-review", response_model=schemas.OverdueReviewResponse)
def secretary_review(
    case_id: int,
    review_id: int,
    review_data: schemas.OverdueSecretaryReview,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    review = db.query(models.OverdueEvidenceReview).join(
        models.Evidence, models.OverdueEvidenceReview.evidence_id == models.Evidence.id
    ).filter(
        models.OverdueEvidenceReview.id == review_id,
        models.Evidence.case_id == case_id
    ).first()
    if not review:
        raise HTTPException(status_code=404, detail="超期审核记录不存在")

    if review.status not in [models.OverdueReviewStatus.PENDING, models.OverdueReviewStatus.ARBITRATOR_REVIEW]:
        raise HTTPException(status_code=400, detail="当前状态不允许秘书审核")

    review.other_party_consent = review_data.other_party_consent
    review.other_party_consent_note = review_data.other_party_consent_note
    review.status = review_data.status
    review.secretary_reviewer_id = current_user.id
    review.secretary_reviewed_at = datetime.now(timezone.utc)

    if review_data.status == models.OverdueReviewStatus.APPROVED:
        evidence = db.query(models.Evidence).filter(models.Evidence.id == review.evidence_id).first()
        if evidence:
            evidence.status = models.EvidenceStatus.SUBMITTED
    elif review_data.status == models.OverdueReviewStatus.REJECTED:
        evidence = db.query(models.Evidence).filter(models.Evidence.id == review.evidence_id).first()
        if evidence:
            evidence.status = models.EvidenceStatus.REJECTED

    db.commit()
    db.refresh(review)
    return review


@router.put("/{review_id}/arbitrator-review", response_model=schemas.OverdueReviewResponse)
def arbitrator_review(
    case_id: int,
    review_id: int,
    review_data: schemas.OverdueArbitratorReview,
    current_user: models.User = Depends(require_roles(models.UserRole.ARBITRATOR, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    review = db.query(models.OverdueEvidenceReview).join(
        models.Evidence, models.OverdueEvidenceReview.evidence_id == models.Evidence.id
    ).filter(
        models.OverdueEvidenceReview.id == review_id,
        models.Evidence.case_id == case_id
    ).first()
    if not review:
        raise HTTPException(status_code=404, detail="超期审核记录不存在")

    if review.status != models.OverdueReviewStatus.ARBITRATOR_REVIEW:
        raise HTTPException(status_code=400, detail="请先由秘书审核并提交仲裁员复核")

    review.arbitrator_opinion = review_data.arbitrator_opinion
    review.affects_hearing_date = review_data.affects_hearing_date
    review.hearing_date_change_note = review_data.hearing_date_change_note
    review.status = review_data.status
    review.arbitrator_reviewer_id = current_user.id
    review.arbitrator_reviewed_at = datetime.now(timezone.utc)

    if review_data.status == models.OverdueReviewStatus.APPROVED:
        evidence = db.query(models.Evidence).filter(models.Evidence.id == review.evidence_id).first()
        if evidence:
            evidence.status = models.EvidenceStatus.SUBMITTED
    elif review_data.status == models.OverdueReviewStatus.REJECTED:
        evidence = db.query(models.Evidence).filter(models.Evidence.id == review.evidence_id).first()
        if evidence:
            evidence.status = models.EvidenceStatus.REJECTED

    db.commit()
    db.refresh(review)
    return review
