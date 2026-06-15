from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_roles
from app.routers.parties import check_case_access

router = APIRouter(prefix="/api/cases/{case_id}/hearings", tags=["庭审引用"])


@router.post("", response_model=schemas.HearingCitationResponse, status_code=status.HTTP_201_CREATED)
def create_hearing_citation(
    case_id: int,
    citation_data: schemas.HearingCitationCreate,
    current_user: models.User = Depends(require_roles(models.UserRole.ARBITRATOR, models.UserRole.SECRETARY, models.UserRole.ADMIN, models.UserRole.CLAIMANT, models.UserRole.RESPONDENT, models.UserRole.AGENT)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    evidence = db.query(models.Evidence).filter(
        models.Evidence.id == citation_data.evidence_id,
        models.Evidence.case_id == case_id
    ).first()
    if not evidence:
        raise HTTPException(status_code=404, detail="证据不存在")

    if evidence.status not in [models.EvidenceStatus.APPROVED, models.EvidenceStatus.SUBMITTED, models.EvidenceStatus.REVIEWING]:
        raise HTTPException(status_code=400, detail="证据未通过审核，无法引用")

    db_citation = models.HearingCitation(
        case_id=case_id,
        cited_by_id=current_user.id,
        **citation_data.model_dump()
    )
    db.add(db_citation)
    db.commit()
    db.refresh(db_citation)
    return db_citation


@router.get("", response_model=List[schemas.HearingCitationResponse])
def list_hearing_citations(
    case_id: int,
    evidence_id: Optional[int] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    query = db.query(models.HearingCitation).filter(
        models.HearingCitation.case_id == case_id
    )
    if evidence_id:
        query = query.filter(models.HearingCitation.evidence_id == evidence_id)

    return query.order_by(models.HearingCitation.cited_at.desc()).all()


@router.get("/dispute-focuses")
def get_dispute_focuses(
    case_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    citations = db.query(models.HearingCitation).filter(
        models.HearingCitation.case_id == case_id,
        models.HearingCitation.dispute_focus.isnot(None)
    ).all()

    focuses = []
    for c in citations:
        if c.dispute_focus and c.dispute_focus.strip():
            focuses.append({
                "id": c.id,
                "evidence_id": c.evidence_id,
                "cited_by_id": c.cited_by_id,
                "dispute_focus": c.dispute_focus,
                "citation_content": c.citation_content,
                "page_reference": c.page_reference,
                "cited_at": c.cited_at
            })

    return {"total": len(focuses), "dispute_focuses": focuses}


@router.get("/evidence-chain")
def get_evidence_chain(
    case_id: int,
    current_user: models.User = Depends(require_roles(models.UserRole.ARBITRATOR, models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    evidences = db.query(models.Evidence).filter(
        models.Evidence.case_id == case_id,
        models.Evidence.status.in_([
            models.EvidenceStatus.APPROVED,
            models.EvidenceStatus.SUBMITTED,
            models.EvidenceStatus.REVIEWING
        ])
    ).order_by(models.Evidence.created_at).all()

    chain = []
    for ev in evidences:
        supplements = db.query(models.SupplementaryMaterial).filter(
            models.SupplementaryMaterial.evidence_id == ev.id
        ).all()
        citations = db.query(models.HearingCitation).filter(
            models.HearingCitation.evidence_id == ev.id
        ).all()
        cross_examinations = db.query(models.CrossExamination).filter(
            models.CrossExamination.evidence_id == ev.id
        ).all()

        chain.append({
            "evidence_id": ev.id,
            "title": ev.title,
            "evidence_type": ev.evidence_type.value,
            "status": ev.status.value,
            "submitter_id": ev.submitter_id,
            "party_id": ev.submitter_party_id,
            "file_hash": ev.file_hash,
            "file_size": ev.file_size,
            "page_count": ev.page_count,
            "created_at": ev.created_at,
            "catalog_id": ev.catalog_id,
            "batch_id": ev.batch_id,
            "is_overdue": ev.is_overdue,
            "is_supplementary": ev.is_supplementary,
            "supplements": [
                {
                    "supplementary_evidence_id": s.supplementary_evidence_id,
                    "reason": s.reason,
                    "created_at": s.created_at
                } for s in supplements
            ],
            "citations": [
                {
                    "cited_by_id": c.cited_by_id,
                    "page_reference": c.page_reference,
                    "dispute_focus": c.dispute_focus,
                    "citation_content": c.citation_content,
                    "cited_at": c.cited_at
                } for c in citations
            ],
            "cross_examinations": [
                {
                    "examiner_id": ce.examiner_id,
                    "party_type": ce.party_type.value,
                    "authenticity": ce.authenticity.value,
                    "relevance": ce.relevance.value,
                    "legality": ce.legality.value,
                    "opinion": ce.opinion,
                    "created_at": ce.created_at
                } for ce in cross_examinations
            ]
        })

    return {
        "case_id": case_id,
        "total_evidences": len(chain),
        "evidence_chain": chain
    }


@router.delete("/{citation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_hearing_citation(
    case_id: int,
    citation_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    citation = db.query(models.HearingCitation).filter(
        models.HearingCitation.id == citation_id,
        models.HearingCitation.case_id == case_id
    ).first()
    if not citation:
        raise HTTPException(status_code=404, detail="庭审引用不存在")

    if citation.cited_by_id != current_user.id and current_user.role not in [models.UserRole.ADMIN, models.UserRole.SECRETARY]:
        raise HTTPException(status_code=403, detail="无权删除此引用")

    db.delete(citation)
    db.commit()
