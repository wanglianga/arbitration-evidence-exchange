from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_roles
from app.routers.parties import check_case_access

router = APIRouter(prefix="/api/cases/{case_id}/cross-examinations", tags=["质证意见"])


@router.post("", response_model=schemas.CrossExaminationResponse, status_code=status.HTTP_201_CREATED)
def create_cross_examination(
    case_id: int,
    ce_data: schemas.CrossExaminationCreate,
    current_user: models.User = Depends(require_roles(models.UserRole.CLAIMANT, models.UserRole.RESPONDENT, models.UserRole.AGENT, models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    evidence = db.query(models.Evidence).filter(
        models.Evidence.id == ce_data.evidence_id,
        models.Evidence.case_id == case_id
    ).first()
    if not evidence:
        raise HTTPException(status_code=404, detail="证据不存在")

    if evidence.status not in [models.EvidenceStatus.SUBMITTED, models.EvidenceStatus.REVIEWING, models.EvidenceStatus.APPROVED]:
        raise HTTPException(status_code=400, detail="证据未提交或未通过审核，无法质证")

    party = db.query(models.Party).filter(
        models.Party.case_id == case_id,
        models.Party.user_id == current_user.id
    ).first()

    agent = None
    if not party:
        agent = db.query(models.Agent).filter(
            models.Agent.case_id == case_id,
            models.Agent.user_id == current_user.id
        ).first()
        if agent and agent.represented_party_id:
            party = db.query(models.Party).filter(models.Party.id == agent.represented_party_id).first()

    if not party and current_user.role not in [models.UserRole.SECRETARY, models.UserRole.ADMIN]:
        raise HTTPException(status_code=400, detail="您不是此案件的当事人或代理人")

    submitter_party = db.query(models.Party).filter(
        models.Party.id == evidence.submitter_party_id
    ).first()

    if party and submitter_party and party.id == submitter_party.id:
        raise HTTPException(status_code=400, detail="不能对自己提交的证据发表质证意见")

    party_type = party.party_type if party else (submitter_party.party_type.value if submitter_party else models.PartyType.RESPONDENT)

    existing = db.query(models.CrossExamination).filter(
        models.CrossExamination.evidence_id == ce_data.evidence_id,
        models.CrossExamination.examiner_id == current_user.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="您已对该证据发表过质证意见，请使用修改接口")

    if ce_data.batch_id:
        batch = db.query(models.ExchangeBatch).filter(
            models.ExchangeBatch.id == ce_data.batch_id,
            models.ExchangeBatch.case_id == case_id
        ).first()
        if not batch:
            raise HTTPException(status_code=404, detail="批次不存在")
        if batch.status != models.ExchangeBatchStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="批次未激活")

    db_ce = models.CrossExamination(
        evidence_id=ce_data.evidence_id,
        batch_id=ce_data.batch_id,
        examiner_id=current_user.id,
        party_type=party_type,
        authenticity=ce_data.authenticity,
        relevance=ce_data.relevance,
        legality=ce_data.legality,
        opinion=ce_data.opinion
    )
    db.add(db_ce)
    db.commit()
    db.refresh(db_ce)
    return db_ce


@router.get("", response_model=List[schemas.CrossExaminationResponse])
def list_cross_examinations(
    case_id: int,
    evidence_id: int = None,
    batch_id: int = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    query = db.query(models.CrossExamination).join(models.Evidence).filter(
        models.Evidence.case_id == case_id
    )
    if evidence_id:
        query = query.filter(models.CrossExamination.evidence_id == evidence_id)
    if batch_id:
        query = query.filter(models.CrossExamination.batch_id == batch_id)

    return query.order_by(models.CrossExamination.created_at.desc()).all()


@router.get("/{ce_id}", response_model=schemas.CrossExaminationResponse)
def get_cross_examination(
    case_id: int,
    ce_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    ce = db.query(models.CrossExamination).join(models.Evidence).filter(
        models.CrossExamination.id == ce_id,
        models.Evidence.case_id == case_id
    ).first()
    if not ce:
        raise HTTPException(status_code=404, detail="质证意见不存在")
    return ce


@router.put("/{ce_id}", response_model=schemas.CrossExaminationResponse)
def update_cross_examination(
    case_id: int,
    ce_id: int,
    ce_data: schemas.CrossExaminationUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    ce = db.query(models.CrossExamination).join(models.Evidence).filter(
        models.CrossExamination.id == ce_id,
        models.Evidence.case_id == case_id
    ).first()
    if not ce:
        raise HTTPException(status_code=404, detail="质证意见不存在")

    if ce.examiner_id != current_user.id and current_user.role not in [models.UserRole.ADMIN, models.UserRole.SECRETARY]:
        raise HTTPException(status_code=403, detail="无权修改此质证意见")

    update_data = ce_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(ce, key, value)

    db.commit()
    db.refresh(ce)
    return ce


@router.delete("/{ce_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cross_examination(
    case_id: int,
    ce_id: int,
    current_user: models.User = Depends(require_roles(models.UserRole.ADMIN, models.UserRole.SECRETARY)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    ce = db.query(models.CrossExamination).join(models.Evidence).filter(
        models.CrossExamination.id == ce_id,
        models.Evidence.case_id == case_id
    ).first()
    if not ce:
        raise HTTPException(status_code=404, detail="质证意见不存在")

    db.delete(ce)
    db.commit()
