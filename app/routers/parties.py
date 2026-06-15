from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_roles

router = APIRouter(prefix="/api/cases/{case_id}/parties", tags=["案件当事人"])


def check_case_access(case_id: int, current_user: models.User, db: Session):
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


@router.post("", response_model=schemas.PartyResponse, status_code=status.HTTP_201_CREATED)
def add_party(
    case_id: int,
    party_data: schemas.PartyCreate,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    user = db.query(models.User).filter(models.User.id == party_data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    existing = db.query(models.Party).filter(
        models.Party.case_id == case_id,
        models.Party.user_id == party_data.user_id,
        models.Party.party_type == party_data.party_type
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="该用户已作为此角色加入案件")

    db_party = models.Party(
        case_id=case_id,
        **party_data.model_dump()
    )
    db.add(db_party)
    db.commit()
    db.refresh(db_party)
    return db_party


@router.get("", response_model=List[schemas.PartyResponse])
def list_parties(
    case_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    parties = db.query(models.Party).filter(
        models.Party.case_id == case_id
    ).all()
    return parties


@router.put("/{party_id}", response_model=schemas.PartyResponse)
def update_party(
    case_id: int,
    party_id: int,
    party_data: schemas.PartyUpdate,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    party = db.query(models.Party).filter(
        models.Party.id == party_id,
        models.Party.case_id == case_id
    ).first()
    if not party:
        raise HTTPException(status_code=404, detail="当事人不存在")

    update_data = party_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(party, key, value)

    db.commit()
    db.refresh(party)
    return party


@router.delete("/{party_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_party(
    case_id: int,
    party_id: int,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    party = db.query(models.Party).filter(
        models.Party.id == party_id,
        models.Party.case_id == case_id
    ).first()
    if not party:
        raise HTTPException(status_code=404, detail="当事人不存在")

    db.delete(party)
    db.commit()
