from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_roles
from app.routers.parties import check_case_access

router = APIRouter(prefix="/api/cases/{case_id}/supplements", tags=["补充材料"])


@router.post("", response_model=schemas.SupplementaryMaterialResponse, status_code=status.HTTP_201_CREATED)
def create_supplement(
    case_id: int,
    supplement_data: schemas.SupplementaryMaterialCreate,
    current_user: models.User = Depends(require_roles(models.UserRole.CLAIMANT, models.UserRole.RESPONDENT, models.UserRole.AGENT, models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    original_evidence = db.query(models.Evidence).filter(
        models.Evidence.id == supplement_data.evidence_id,
        models.Evidence.case_id == case_id
    ).first()
    if not original_evidence:
        raise HTTPException(status_code=404, detail="原证据不存在")

    supplementary_evidence = db.query(models.Evidence).filter(
        models.Evidence.id == supplement_data.supplementary_evidence_id,
        models.Evidence.case_id == case_id
    ).first()
    if not supplementary_evidence:
        raise HTTPException(status_code=404, detail="补充证据不存在")

    if supplement_data.evidence_id == supplement_data.supplementary_evidence_id:
        raise HTTPException(status_code=400, detail="原证据和补充证据不能相同")

    if original_evidence.submitter_id != current_user.id and current_user.role not in [models.UserRole.ADMIN, models.UserRole.SECRETARY]:
        raise HTTPException(status_code=403, detail="只能为自己提交的证据添加补充材料")

    if supplementary_evidence.submitter_id != original_evidence.submitter_id:
        raise HTTPException(status_code=400, detail="补充证据必须与原证据为同一提交人")

    supplementary_evidence.is_supplementary = True

    existing = db.query(models.SupplementaryMaterial).filter(
        models.SupplementaryMaterial.evidence_id == supplement_data.evidence_id,
        models.SupplementaryMaterial.supplementary_evidence_id == supplement_data.supplementary_evidence_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="已存在相同的补充关系")

    db_supplement = models.SupplementaryMaterial(**supplement_data.model_dump())
    db.add(db_supplement)
    db.commit()
    db.refresh(db_supplement)
    return db_supplement


@router.get("", response_model=List[schemas.SupplementaryMaterialResponse])
def list_supplements(
    case_id: int,
    evidence_id: Optional[int] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    query = db.query(models.SupplementaryMaterial).join(
        models.Evidence, models.SupplementaryMaterial.evidence_id == models.Evidence.id
    ).filter(models.Evidence.case_id == case_id)

    if evidence_id:
        query = query.filter(
            (models.SupplementaryMaterial.evidence_id == evidence_id) |
            (models.SupplementaryMaterial.supplementary_evidence_id == evidence_id)
        )

    return query.all()


@router.delete("/{supplement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplement(
    case_id: int,
    supplement_id: int,
    current_user: models.User = Depends(require_roles(models.UserRole.ADMIN, models.UserRole.SECRETARY)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    supplement = db.query(models.SupplementaryMaterial).join(
        models.Evidence, models.SupplementaryMaterial.evidence_id == models.Evidence.id
    ).filter(
        models.SupplementaryMaterial.id == supplement_id,
        models.Evidence.case_id == case_id
    ).first()
    if not supplement:
        raise HTTPException(status_code=404, detail="补充材料记录不存在")

    supplementary_evidence = db.query(models.Evidence).filter(
        models.Evidence.id == supplement.supplementary_evidence_id
    ).first()
    if supplementary_evidence:
        other_links = db.query(models.SupplementaryMaterial).filter(
            models.SupplementaryMaterial.supplementary_evidence_id == supplement.supplementary_evidence_id,
            models.SupplementaryMaterial.id != supplement_id
        ).count()
        if other_links == 0:
            supplementary_evidence.is_supplementary = False

    db.delete(supplement)
    db.commit()
