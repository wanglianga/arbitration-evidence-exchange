from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timezone

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_roles
from app.routers.parties import check_case_access

router = APIRouter(prefix="/api/cases/{case_id}/batches", tags=["交换批次"])


@router.post("", response_model=schemas.ExchangeBatchResponse, status_code=status.HTTP_201_CREATED)
def create_batch(
    case_id: int,
    batch_data: schemas.ExchangeBatchCreate,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    last_batch = db.query(models.ExchangeBatch).filter(
        models.ExchangeBatch.case_id == case_id
    ).order_by(models.ExchangeBatch.batch_number.desc()).first()
    next_number = last_batch.batch_number + 1 if last_batch else 1

    db_batch = models.ExchangeBatch(
        case_id=case_id,
        batch_number=next_number,
        created_by=current_user.id,
        **batch_data.model_dump()
    )
    db.add(db_batch)
    db.commit()
    db.refresh(db_batch)
    return db_batch


@router.get("", response_model=List[schemas.ExchangeBatchResponse])
def list_batches(
    case_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    batches = db.query(models.ExchangeBatch).filter(
        models.ExchangeBatch.case_id == case_id
    ).order_by(models.ExchangeBatch.batch_number).all()
    return batches


@router.get("/{batch_id}", response_model=schemas.ExchangeBatchResponse)
def get_batch(
    case_id: int,
    batch_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    batch = db.query(models.ExchangeBatch).filter(
        models.ExchangeBatch.id == batch_id,
        models.ExchangeBatch.case_id == case_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="交换批次不存在")
    return batch


@router.put("/{batch_id}", response_model=schemas.ExchangeBatchResponse)
def update_batch(
    case_id: int,
    batch_id: int,
    batch_data: schemas.ExchangeBatchUpdate,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    batch = db.query(models.ExchangeBatch).filter(
        models.ExchangeBatch.id == batch_id,
        models.ExchangeBatch.case_id == case_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="交换批次不存在")

    if batch.is_frozen:
        raise HTTPException(status_code=400, detail="批次已提交冻结，无法修改")

    if batch.status == models.ExchangeBatchStatus.CLOSED:
        raise HTTPException(status_code=400, detail="批次已关闭，无法修改")

    update_data = batch_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(batch, key, value)

    db.commit()
    db.refresh(batch)
    return batch


@router.post("/{batch_id}/activate", response_model=schemas.ExchangeBatchResponse)
def activate_batch(
    case_id: int,
    batch_id: int,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    batch = db.query(models.ExchangeBatch).filter(
        models.ExchangeBatch.id == batch_id,
        models.ExchangeBatch.case_id == case_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="交换批次不存在")

    if batch.status != models.ExchangeBatchStatus.DRAFT:
        raise HTTPException(status_code=400, detail="只有草稿状态的批次可以激活")

    batch.status = models.ExchangeBatchStatus.ACTIVE
    batch.activated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(batch)
    return batch


@router.post("/{batch_id}/submit", response_model=schemas.ExchangeBatchResponse)
def submit_batch(
    case_id: int,
    batch_id: int,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN, models.UserRole.CLAIMANT, models.UserRole.RESPONDENT, models.UserRole.AGENT)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    batch = db.query(models.ExchangeBatch).filter(
        models.ExchangeBatch.id == batch_id,
        models.ExchangeBatch.case_id == case_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="交换批次不存在")

    if batch.status not in [models.ExchangeBatchStatus.ACTIVE, models.ExchangeBatchStatus.DRAFT]:
        raise HTTPException(status_code=400, detail="只有草稿或激活状态的批次可以提交")

    batch.status = models.ExchangeBatchStatus.SUBMITTED
    batch.submitted_at = datetime.now(timezone.utc)
    batch.submitted_by = current_user.id
    batch.is_frozen = True
    batch.frozen_at = datetime.now(timezone.utc)
    batch.frozen_by = current_user.id

    evidences = db.query(models.Evidence).filter(
        models.Evidence.batch_id == batch_id
    ).all()
    for evidence in evidences:
        last_version = db.query(models.EvidenceVersionHistory).filter(
            models.EvidenceVersionHistory.evidence_id == evidence.id
        ).order_by(models.EvidenceVersionHistory.version_number.desc()
        ).first()
        next_version = (last_version.version_number + 1) if last_version else 1

        version_entry = models.EvidenceVersionHistory(
            evidence_id=evidence.id,
            version_number=next_version,
            title=evidence.title,
            description=evidence.description,
            evidence_type=evidence.evidence_type,
            catalog_id=evidence.catalog_id,
            page_count=evidence.page_count,
            file_hash=evidence.file_hash,
            file_size=evidence.file_size,
            file_path=evidence.file_path,
            file_name=evidence.file_name,
            mime_type=evidence.mime_type,
            visibility=evidence.visibility,
            changed_by=current_user.id,
            change_reason="批次提交冻结版本"
        )
        db.add(version_entry)

    db.commit()
    db.refresh(batch)
    return batch


@router.post("/{batch_id}/close", response_model=schemas.ExchangeBatchResponse)
def close_batch(
    case_id: int,
    batch_id: int,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    batch = db.query(models.ExchangeBatch).filter(
        models.ExchangeBatch.id == batch_id,
        models.ExchangeBatch.case_id == case_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="交换批次不存在")

    if batch.status not in [models.ExchangeBatchStatus.ACTIVE, models.ExchangeBatchStatus.SUBMITTED]:
        raise HTTPException(status_code=400, detail="只有激活或已提交状态的批次可以关闭")

    batch.status = models.ExchangeBatchStatus.CLOSED
    batch.closed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(batch)
    return batch


@router.delete("/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_batch(
    case_id: int,
    batch_id: int,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    batch = db.query(models.ExchangeBatch).filter(
        models.ExchangeBatch.id == batch_id,
        models.ExchangeBatch.case_id == case_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="交换批次不存在")

    if batch.status != models.ExchangeBatchStatus.DRAFT:
        raise HTTPException(status_code=400, detail="只有草稿状态的批次可以删除")

    evidence_count = db.query(models.Evidence).filter(
        models.Evidence.batch_id == batch_id
    ).count()
    if evidence_count > 0:
        raise HTTPException(status_code=400, detail="批次下存在证据，无法删除")

    db.delete(batch)
    db.commit()
