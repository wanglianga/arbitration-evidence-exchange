from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import os

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_roles
from app.routers.parties import check_case_access
from app.config import settings

router = APIRouter(prefix="/api/cases/{case_id}/evidences", tags=["证据管理"])


def check_evidence_visibility(evidence: models.Evidence, current_user: models.User, db: Session):
    if current_user.role in [models.UserRole.ADMIN, models.UserRole.SECRETARY, models.UserRole.ARBITRATOR]:
        return True

    if evidence.visibility == models.VisibilityScope.ALL:
        return True

    claimant_party = db.query(models.Party).filter(
        models.Party.case_id == evidence.case_id,
        models.Party.party_type == models.PartyType.CLAIMANT,
        models.Party.user_id == current_user.id
    ).first()
    respondent_party = db.query(models.Party).filter(
        models.Party.case_id == evidence.case_id,
        models.Party.party_type == models.PartyType.RESPONDENT,
        models.Party.user_id == current_user.id
    ).first()
    is_agent = db.query(models.Agent).filter(
        models.Agent.case_id == evidence.case_id,
        models.Agent.user_id == current_user.id
    ).first()

    if evidence.visibility == models.VisibilityScope.CLAIMANT_ONLY:
        return bool(claimant_party) or (is_agent and is_agent.represented_party and is_agent.represented_party.party_type == models.PartyType.CLAIMANT)
    if evidence.visibility == models.VisibilityScope.RESPONDENT_ONLY:
        return bool(respondent_party) or (is_agent and is_agent.represented_party and is_agent.represented_party.party_type == models.PartyType.RESPONDENT)
    if evidence.visibility == models.VisibilityScope.SECRETARY_ONLY:
        return False
    if evidence.visibility == models.VisibilityScope.ARBITRATOR_ONLY:
        return False

    return True


@router.post("", response_model=schemas.EvidenceResponse, status_code=status.HTTP_201_CREATED)
def create_evidence(
    case_id: int,
    evidence_data: schemas.EvidenceCreate,
    current_user: models.User = Depends(require_roles(models.UserRole.CLAIMANT, models.UserRole.RESPONDENT, models.UserRole.AGENT, models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    catalog = db.query(models.EvidenceCatalog).filter(
        models.EvidenceCatalog.id == evidence_data.catalog_id,
        models.EvidenceCatalog.case_id == case_id
    ).first()
    if not catalog:
        raise HTTPException(status_code=404, detail="证据目录不存在")

    if catalog.is_frozen:
        raise HTTPException(status_code=400, detail="证据目录已冻结，无法添加证据")

    submitter_party = db.query(models.Party).filter(
        models.Party.case_id == case_id,
        models.Party.user_id == current_user.id
    ).first()

    if not submitter_party and current_user.role in [models.UserRole.CLAIMANT, models.UserRole.RESPONDENT]:
        raise HTTPException(status_code=400, detail="您不是此案件的当事人")

    file_hash = None
    file_size = None
    file_path = None
    file_name = None
    mime_type = None
    is_overdue = False

    if evidence_data.upload_id:
        chunk_upload = db.query(models.ChunkUpload).filter(
            models.ChunkUpload.upload_id == evidence_data.upload_id
        ).first()
        if not chunk_upload:
            raise HTTPException(status_code=404, detail="上传记录不存在")
        if chunk_upload.status != models.UploadStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="文件上传未完成")
        if chunk_upload.user_id != current_user.id and current_user.role not in [models.UserRole.ADMIN, models.UserRole.SECRETARY]:
            raise HTTPException(status_code=403, detail="无权使用此上传文件")

        file_hash = chunk_upload.file_hash
        file_size = chunk_upload.file_size
        file_name = chunk_upload.file_name
        mime_type = chunk_upload.mime_type
        ext = os.path.splitext(chunk_upload.file_name)[1]
        final_filename = f"{chunk_upload.upload_id}{ext}"
        file_path = os.path.join(settings.UPLOAD_DIR, "files", final_filename)

        if not os.path.exists(file_path):
            raise HTTPException(status_code=400, detail="文件不存在")

    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if case.evidence_deadline and datetime.utcnow() > case.evidence_deadline:
        is_overdue = True

    db_evidence = models.Evidence(
        case_id=case_id,
        catalog_id=evidence_data.catalog_id,
        batch_id=evidence_data.batch_id,
        title=evidence_data.title,
        description=evidence_data.description,
        evidence_type=evidence_data.evidence_type,
        visibility=evidence_data.visibility,
        page_count=evidence_data.page_count,
        file_hash=file_hash,
        file_size=file_size,
        file_path=file_path,
        file_name=file_name,
        mime_type=mime_type,
        submitter_id=current_user.id,
        submitter_party_id=submitter_party.id if submitter_party else None,
        is_overdue=is_overdue
    )
    db.add(db_evidence)
    db.commit()
    db.refresh(db_evidence)
    return db_evidence


@router.get("", response_model=List[schemas.EvidenceResponse])
def list_evidences(
    case_id: int,
    status_filter: Optional[models.EvidenceStatus] = None,
    type_filter: Optional[models.EvidenceType] = None,
    catalog_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    query = db.query(models.Evidence).filter(models.Evidence.case_id == case_id)

    if status_filter:
        query = query.filter(models.Evidence.status == status_filter)
    if type_filter:
        query = query.filter(models.Evidence.evidence_type == type_filter)
    if catalog_id:
        query = query.filter(models.Evidence.catalog_id == catalog_id)
    if batch_id:
        query = query.filter(models.Evidence.batch_id == batch_id)

    evidences = query.order_by(models.Evidence.created_at.desc()).offset(skip).limit(limit).all()

    visible_evidences = [
        e for e in evidences
        if check_evidence_visibility(e, current_user, db)
    ]
    return visible_evidences


@router.get("/{evidence_id}", response_model=schemas.EvidenceResponse)
def get_evidence(
    case_id: int,
    evidence_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    evidence = db.query(models.Evidence).filter(
        models.Evidence.id == evidence_id,
        models.Evidence.case_id == case_id
    ).first()
    if not evidence:
        raise HTTPException(status_code=404, detail="证据不存在")

    if not check_evidence_visibility(evidence, current_user, db):
        raise HTTPException(status_code=403, detail="无权查看此证据")

    return evidence


@router.put("/{evidence_id}", response_model=schemas.EvidenceResponse)
def update_evidence(
    case_id: int,
    evidence_id: int,
    evidence_data: schemas.EvidenceUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    evidence = db.query(models.Evidence).filter(
        models.Evidence.id == evidence_id,
        models.Evidence.case_id == case_id
    ).first()
    if not evidence:
        raise HTTPException(status_code=404, detail="证据不存在")

    if evidence.status == models.EvidenceStatus.WITHDRAWN:
        raise HTTPException(status_code=400, detail="证据已撤回，无法修改")

    if evidence.submitter_id != current_user.id and current_user.role not in [models.UserRole.ADMIN, models.UserRole.SECRETARY]:
        raise HTTPException(status_code=403, detail="无权修改此证据")

    if evidence_data.catalog_id and evidence_data.catalog_id != evidence.catalog_id:
        new_catalog = db.query(models.EvidenceCatalog).filter(
            models.EvidenceCatalog.id == evidence_data.catalog_id,
            models.EvidenceCatalog.case_id == case_id
        ).first()
        if not new_catalog:
            raise HTTPException(status_code=404, detail="新的证据目录不存在")
        if new_catalog.is_frozen:
            raise HTTPException(status_code=400, detail="目标证据目录已冻结")

    update_data = evidence_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(evidence, key, value)

    db.commit()
    db.refresh(evidence)
    return evidence


@router.post("/{evidence_id}/submit", response_model=schemas.EvidenceResponse)
def submit_evidence(
    case_id: int,
    evidence_id: int,
    current_user: models.User = Depends(require_roles(models.UserRole.CLAIMANT, models.UserRole.RESPONDENT, models.UserRole.AGENT, models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    evidence = db.query(models.Evidence).filter(
        models.Evidence.id == evidence_id,
        models.Evidence.case_id == case_id
    ).first()
    if not evidence:
        raise HTTPException(status_code=404, detail="证据不存在")

    if evidence.status not in [models.EvidenceStatus.DRAFT, models.EvidenceStatus.REJECTED]:
        raise HTTPException(status_code=400, detail=f"当前状态 {evidence.status.value} 无法提交")

    if evidence.submitter_id != current_user.id and current_user.role not in [models.UserRole.ADMIN, models.UserRole.SECRETARY]:
        raise HTTPException(status_code=403, detail="无权提交此证据")

    if not evidence.file_path:
        raise HTTPException(status_code=400, detail="请先上传证据文件")

    evidence.status = models.EvidenceStatus.SUBMITTED
    db.commit()
    db.refresh(evidence)
    return evidence


@router.post("/{evidence_id}/withdraw", response_model=schemas.EvidenceResponse)
def withdraw_evidence(
    case_id: int,
    evidence_id: int,
    withdraw_data: schemas.EvidenceWithdrawRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    evidence = db.query(models.Evidence).filter(
        models.Evidence.id == evidence_id,
        models.Evidence.case_id == case_id
    ).first()
    if not evidence:
        raise HTTPException(status_code=404, detail="证据不存在")

    if evidence.status == models.EvidenceStatus.WITHDRAWN:
        raise HTTPException(status_code=400, detail="证据已撤回")

    if evidence.submitter_id != current_user.id and current_user.role not in [models.UserRole.ADMIN, models.UserRole.SECRETARY]:
        raise HTTPException(status_code=403, detail="无权撤回此证据")

    evidence.status = models.EvidenceStatus.WITHDRAWN
    evidence.withdrawn_at = datetime.utcnow()
    evidence.withdrawn_reason = withdraw_data.reason
    evidence.withdrawn_by = current_user.id

    db.commit()
    db.refresh(evidence)
    return evidence


@router.delete("/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evidence(
    case_id: int,
    evidence_id: int,
    current_user: models.User = Depends(require_roles(models.UserRole.ADMIN, models.UserRole.SECRETARY)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    evidence = db.query(models.Evidence).filter(
        models.Evidence.id == evidence_id,
        models.Evidence.case_id == case_id
    ).first()
    if not evidence:
        raise HTTPException(status_code=404, detail="证据不存在")

    if evidence.status not in [models.EvidenceStatus.DRAFT, models.EvidenceStatus.WITHDRAWN]:
        raise HTTPException(status_code=400, detail="只有草稿或已撤回状态的证据可以删除")

    db.delete(evidence)
    db.commit()
