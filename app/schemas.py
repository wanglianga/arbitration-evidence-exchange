from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
import enum

from app.models import (
    UserRole, CaseStatus, PartyType, EvidenceType, EvidenceStatus,
    ExchangeBatchStatus, CrossExaminationOpinion, RelevanceOpinion,
    LegalityOpinion, VisibilityScope, ReviewStatus, UploadStatus
)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


class UserBase(BaseModel):
    username: str
    email: EmailStr
    full_name: str
    phone: Optional[str] = None
    role: UserRole


class UserCreate(UserBase):
    password: str


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    password: Optional[str] = None


class CaseBase(BaseModel):
    title: str
    description: Optional[str] = None
    arbitration_tribunal: Optional[str] = None
    case_amount: Optional[float] = None
    accepted_at: Optional[datetime] = None
    hearing_at: Optional[datetime] = None
    evidence_deadline: Optional[datetime] = None


class CaseCreate(CaseBase):
    case_number: str


class CaseUpdate(CaseBase):
    case_number: Optional[str] = None
    status: Optional[CaseStatus] = None


class CaseResponse(CaseBase):
    id: int
    case_number: str
    status: CaseStatus
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PartyBase(BaseModel):
    party_type: PartyType
    company_name: Optional[str] = None
    legal_representative: Optional[str] = None
    address: Optional[str] = None
    is_company: bool = False


class PartyCreate(PartyBase):
    user_id: int


class PartyUpdate(BaseModel):
    company_name: Optional[str] = None
    legal_representative: Optional[str] = None
    address: Optional[str] = None
    is_company: Optional[bool] = None


class PartyResponse(PartyBase):
    id: int
    case_id: int
    user_id: int
    user: Optional[UserResponse] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AgentBase(BaseModel):
    user_id: int
    represented_party_id: Optional[int] = None
    authorization_scope: Optional[str] = None


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    represented_party_id: Optional[int] = None
    authorization_scope: Optional[str] = None


class AgentResponse(AgentBase):
    id: int
    case_id: int
    user: Optional[UserResponse] = None
    created_at: datetime

    class Config:
        from_attributes = True


class EvidenceCatalogBase(BaseModel):
    name: str
    parent_id: Optional[int] = None
    order_index: int = 0


class EvidenceCatalogCreate(EvidenceCatalogBase):
    pass


class EvidenceCatalogUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None
    order_index: Optional[int] = None


class EvidenceCatalogResponse(EvidenceCatalogBase):
    id: int
    case_id: int
    is_frozen: bool
    frozen_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    children: List["EvidenceCatalogResponse"] = []

    class Config:
        from_attributes = True


EvidenceCatalogResponse.model_rebuild()


class EvidenceBase(BaseModel):
    title: str
    description: Optional[str] = None
    evidence_type: EvidenceType = EvidenceType.OTHER
    visibility: VisibilityScope = VisibilityScope.ALL
    page_count: int = 0


class EvidenceCreate(EvidenceBase):
    catalog_id: int
    batch_id: Optional[int] = None
    upload_id: Optional[str] = None


class EvidenceUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    evidence_type: Optional[EvidenceType] = None
    visibility: Optional[VisibilityScope] = None
    page_count: Optional[int] = None
    catalog_id: Optional[int] = None
    batch_id: Optional[int] = None


class EvidenceResponse(EvidenceBase):
    id: int
    case_id: int
    catalog_id: int
    batch_id: Optional[int] = None
    status: EvidenceStatus
    file_hash: Optional[str] = None
    file_size: Optional[int] = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    is_supplementary: bool
    is_overdue: bool
    submitter_id: int
    submitter_party_id: Optional[int] = None
    withdrawn_at: Optional[datetime] = None
    withdrawn_reason: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EvidenceWithdrawRequest(BaseModel):
    reason: str


class EvidenceSubmitRequest(BaseModel):
    pass


class ExchangeBatchBase(BaseModel):
    name: str
    description: Optional[str] = None
    visibility: VisibilityScope = VisibilityScope.ALL
    deadline: Optional[datetime] = None


class ExchangeBatchCreate(ExchangeBatchBase):
    pass


class ExchangeBatchUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    visibility: Optional[VisibilityScope] = None
    deadline: Optional[datetime] = None
    status: Optional[ExchangeBatchStatus] = None


class ExchangeBatchResponse(ExchangeBatchBase):
    id: int
    case_id: int
    batch_number: int
    status: ExchangeBatchStatus
    created_by: Optional[int] = None
    activated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CrossExaminationBase(BaseModel):
    authenticity: CrossExaminationOpinion = CrossExaminationOpinion.NO_OPINION
    relevance: RelevanceOpinion = RelevanceOpinion.NO_OPINION
    legality: LegalityOpinion = LegalityOpinion.NO_OPINION
    opinion: Optional[str] = None


class CrossExaminationCreate(CrossExaminationBase):
    evidence_id: int
    batch_id: Optional[int] = None


class CrossExaminationUpdate(CrossExaminationBase):
    pass


class CrossExaminationResponse(CrossExaminationBase):
    id: int
    evidence_id: int
    batch_id: Optional[int] = None
    examiner_id: int
    party_type: PartyType
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EvidenceReviewBase(BaseModel):
    format_ok: Optional[bool] = None
    desensitization_ok: Optional[bool] = None
    page_number_ok: Optional[bool] = None
    comment: Optional[str] = None


class EvidenceReviewCreate(EvidenceReviewBase):
    evidence_id: int
    status: ReviewStatus = ReviewStatus.PENDING


class EvidenceReviewUpdate(EvidenceReviewBase):
    status: Optional[ReviewStatus] = None


class EvidenceReviewResponse(EvidenceReviewBase):
    id: int
    evidence_id: int
    reviewer_id: int
    status: ReviewStatus
    reviewed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SupplementaryMaterialBase(BaseModel):
    evidence_id: int
    supplementary_evidence_id: int
    reason: Optional[str] = None


class SupplementaryMaterialCreate(SupplementaryMaterialBase):
    pass


class SupplementaryMaterialResponse(SupplementaryMaterialBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class HearingCitationBase(BaseModel):
    evidence_id: int
    page_reference: Optional[str] = None
    dispute_focus: Optional[str] = None
    citation_content: Optional[str] = None


class HearingCitationCreate(HearingCitationBase):
    pass


class HearingCitationResponse(HearingCitationBase):
    id: int
    case_id: int
    cited_by_id: int
    cited_at: datetime

    class Config:
        from_attributes = True


class ChunkUploadInitRequest(BaseModel):
    file_name: str
    file_size: int
    total_chunks: int
    chunk_size: int
    mime_type: Optional[str] = None
    case_id: Optional[int] = None


class ChunkUploadInitResponse(BaseModel):
    upload_id: str
    status: UploadStatus
    created_at: datetime


class ChunkUploadResponse(BaseModel):
    upload_id: str
    chunk_number: int
    uploaded_chunks: int
    total_chunks: int
    status: UploadStatus
    file_hash: Optional[str] = None
    file_path: Optional[str] = None
    completed: bool


class ChunkUploadStatusResponse(BaseModel):
    upload_id: str
    file_name: str
    file_size: int
    total_chunks: int
    uploaded_chunks: int
    chunk_size: int
    status: UploadStatus
    file_hash: Optional[str] = None
    completed_at: Optional[datetime] = None
    file_path: Optional[str] = None


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List
