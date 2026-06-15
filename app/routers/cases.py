from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_roles

router = APIRouter(prefix="/api/cases", tags=["案件管理"])


@router.post("", response_model=schemas.CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(
    case_data: schemas.CaseCreate,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    existing = db.query(models.Case).filter(models.Case.case_number == case_data.case_number).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="案件编号已存在"
        )

    db_case = models.Case(
        **case_data.model_dump(),
        created_by=current_user.id
    )
    db.add(db_case)
    db.commit()
    db.refresh(db_case)
    return db_case


@router.get("", response_model=List[schemas.CaseResponse])
def list_cases(
    status_filter: Optional[models.CaseStatus] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(models.Case)

    if current_user.role not in [models.UserRole.ADMIN, models.UserRole.SECRETARY, models.UserRole.ARBITRATOR]:
        party_case_ids = [p.case_id for p in db.query(models.Party).filter(models.Party.user_id == current_user.id).all()]
        agent_case_ids = [a.case_id for a in db.query(models.Agent).filter(models.Agent.user_id == current_user.id).all()]
        accessible_case_ids = list(set(party_case_ids + agent_case_ids))
        query = query.filter(models.Case.id.in_(accessible_case_ids))

    if status_filter:
        query = query.filter(models.Case.status == status_filter)

    cases = query.order_by(models.Case.created_at.desc()).offset(skip).limit(limit).all()
    return cases


@router.get("/{case_id}", response_model=schemas.CaseResponse)
def get_case(
    case_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    if current_user.role not in [models.UserRole.ADMIN, models.UserRole.SECRETARY, models.UserRole.ARBITRATOR]:
        is_party = db.query(models.Party).filter(
            models.Party.case_id == case_id,
            models.Party.user_id == current_user.id
        ).first()
        is_agent = db.query(models.Agent).filter(
            models.Agent.case_id == case_id,
            models.Agent.user_id == current_user.id
        ).first()
        if not is_party and not is_agent:
            raise HTTPException(status_code=403, detail="无权访问此案件")

    return case


@router.put("/{case_id}", response_model=schemas.CaseResponse)
def update_case(
    case_id: int,
    case_data: schemas.CaseUpdate,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    update_data = case_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(case, key, value)

    db.commit()
    db.refresh(case)
    return case


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(
    case_id: int,
    current_user: models.User = Depends(require_roles(models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    db.delete(case)
    db.commit()
