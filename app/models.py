from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, ForeignKey,
    Enum, Float, BigInteger
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


class UserRole(str, enum.Enum):
    CLAIMANT = "claimant"
    RESPONDENT = "respondent"
    AGENT = "agent"
    SECRETARY = "secretary"
    ARBITRATOR = "arbitrator"
    ADMIN = "admin"


class CaseStatus(str, enum.Enum):
    DRAFT = "draft"
    ACCEPTED = "accepted"
    EVIDENCE_EXCHANGE = "evidence_exchange"
    HEARING = "hearing"
    DECIDED = "decided"
    CLOSED = "closed"


class PartyType(str, enum.Enum):
    CLAIMANT = "claimant"
    RESPONDENT = "respondent"


class EvidenceType(str, enum.Enum):
    CONTRACT = "contract"
    CHAT_RECORD = "chat_record"
    PAYMENT_PROOF = "payment_proof"
    ACCEPTANCE_MATERIAL = "acceptance_material"
    LOSS_STATEMENT = "loss_statement"
    OTHER = "other"


class EvidenceStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    SUPPLEMENTARY = "supplementary"


class ExchangeBatchStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"


class CrossExaminationOpinion(str, enum.Enum):
    TRUE = "true"
    FALSE = "false"
    PARTIALLY_TRUE = "partially_true"
    NO_OPINION = "no_opinion"


class RelevanceOpinion(str, enum.Enum):
    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"
    PARTIALLY_RELEVANT = "partially_relevant"
    NO_OPINION = "no_opinion"


class LegalityOpinion(str, enum.Enum):
    LEGAL = "legal"
    ILLEGAL = "illegal"
    PARTIALLY_LEGAL = "partially_legal"
    NO_OPINION = "no_opinion"


class VisibilityScope(str, enum.Enum):
    ALL = "all"
    CLAIMANT_ONLY = "claimant_only"
    RESPONDENT_ONLY = "respondent_only"
    SECRETARY_ONLY = "secretary_only"
    ARBITRATOR_ONLY = "arbitrator_only"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class UploadStatus(str, enum.Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(200), nullable=False)
    phone = Column(String(20))
    role = Column(Enum(UserRole), nullable=False, default=UserRole.CLAIMANT)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    parties = relationship("Party", back_populates="user")
    agents = relationship("Agent", back_populates="user")
    submitted_evidences = relationship("Evidence", back_populates="submitter", foreign_keys="Evidence.submitter_id")
    cross_examinations = relationship("CrossExamination", back_populates="examiner")
    hearings = relationship("HearingCitation", back_populates="cited_by")
    reviews = relationship("EvidenceReview", back_populates="reviewer")


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    case_number = Column(String(50), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    status = Column(Enum(CaseStatus), nullable=False, default=CaseStatus.DRAFT)
    arbitration_tribunal = Column(String(200))
    case_amount = Column(Float)
    accepted_at = Column(DateTime(timezone=True))
    hearing_at = Column(DateTime(timezone=True))
    evidence_deadline = Column(DateTime(timezone=True))
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    parties = relationship("Party", back_populates="case", cascade="all, delete-orphan")
    agents = relationship("Agent", back_populates="case", cascade="all, delete-orphan")
    evidence_catalogs = relationship("EvidenceCatalog", back_populates="case", cascade="all, delete-orphan")
    exchange_batches = relationship("ExchangeBatch", back_populates="case", cascade="all, delete-orphan")
    hearings = relationship("HearingCitation", back_populates="case", cascade="all, delete-orphan")


class Party(Base):
    __tablename__ = "parties"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    party_type = Column(Enum(PartyType), nullable=False)
    company_name = Column(String(500))
    legal_representative = Column(String(200))
    address = Column(Text)
    is_company = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("Case", back_populates="parties")
    user = relationship("User", back_populates="parties")
    evidences = relationship("Evidence", back_populates="submitter_party")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    represented_party_id = Column(Integer, ForeignKey("parties.id"))
    authorization_scope = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("Case", back_populates="agents")
    user = relationship("User", back_populates="agents")
    represented_party = relationship("Party")


class EvidenceCatalog(Base):
    __tablename__ = "evidence_catalogs"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    name = Column(String(500), nullable=False)
    parent_id = Column(Integer, ForeignKey("evidence_catalogs.id"))
    order_index = Column(Integer, default=0)
    is_frozen = Column(Boolean, default=False)
    frozen_at = Column(DateTime(timezone=True))
    frozen_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    case = relationship("Case", back_populates="evidence_catalogs")
    parent = relationship("EvidenceCatalog", remote_side=[id])
    children = relationship("EvidenceCatalog", back_populates="parent")
    evidences = relationship("Evidence", back_populates="catalog")


class Evidence(Base):
    __tablename__ = "evidences"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    catalog_id = Column(Integer, ForeignKey("evidence_catalogs.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("exchange_batches.id"))
    title = Column(String(500), nullable=False)
    description = Column(Text)
    evidence_type = Column(Enum(EvidenceType), nullable=False, default=EvidenceType.OTHER)
    status = Column(Enum(EvidenceStatus), nullable=False, default=EvidenceStatus.DRAFT)
    visibility = Column(Enum(VisibilityScope), nullable=False, default=VisibilityScope.ALL)
    page_count = Column(Integer, default=0)
    file_hash = Column(String(128))
    file_size = Column(BigInteger)
    file_path = Column(String(1000))
    file_name = Column(String(500))
    mime_type = Column(String(200))
    is_supplementary = Column(Boolean, default=False)
    is_overdue = Column(Boolean, default=False)
    submitter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitter_party_id = Column(Integer, ForeignKey("parties.id"))
    withdrawn_at = Column(DateTime(timezone=True))
    withdrawn_reason = Column(Text)
    withdrawn_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    catalog = relationship("EvidenceCatalog", back_populates="evidences")
    submitter = relationship("User", back_populates="submitted_evidences", foreign_keys=[submitter_id])
    submitter_party = relationship("Party", back_populates="evidences")
    batch = relationship("ExchangeBatch", back_populates="evidences")
    cross_examinations = relationship("CrossExamination", back_populates="evidence", cascade="all, delete-orphan")
    reviews = relationship("EvidenceReview", back_populates="evidence", cascade="all, delete-orphan")
    hearing_citations = relationship("HearingCitation", back_populates="evidence")
    supplements = relationship("SupplementaryMaterial", back_populates="evidence", cascade="all, delete-orphan", foreign_keys="SupplementaryMaterial.evidence_id")
    supplementary_of = relationship("SupplementaryMaterial", back_populates="supplementary_evidence", uselist=False, foreign_keys="SupplementaryMaterial.supplementary_evidence_id")


class ExchangeBatch(Base):
    __tablename__ = "exchange_batches"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    batch_number = Column(Integer, nullable=False)
    name = Column(String(500), nullable=False)
    description = Column(Text)
    status = Column(Enum(ExchangeBatchStatus), nullable=False, default=ExchangeBatchStatus.DRAFT)
    visibility = Column(Enum(VisibilityScope), nullable=False, default=VisibilityScope.ALL)
    deadline = Column(DateTime(timezone=True))
    created_by = Column(Integer, ForeignKey("users.id"))
    activated_at = Column(DateTime(timezone=True))
    closed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    case = relationship("Case", back_populates="exchange_batches")
    evidences = relationship("Evidence", back_populates="batch")
    cross_examinations = relationship("CrossExamination", back_populates="batch")


class CrossExamination(Base):
    __tablename__ = "cross_examinations"

    id = Column(Integer, primary_key=True, index=True)
    evidence_id = Column(Integer, ForeignKey("evidences.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("exchange_batches.id"))
    examiner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    party_type = Column(Enum(PartyType), nullable=False)
    authenticity = Column(Enum(CrossExaminationOpinion), nullable=False, default=CrossExaminationOpinion.NO_OPINION)
    relevance = Column(Enum(RelevanceOpinion), nullable=False, default=RelevanceOpinion.NO_OPINION)
    legality = Column(Enum(LegalityOpinion), nullable=False, default=LegalityOpinion.NO_OPINION)
    opinion = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    evidence = relationship("Evidence", back_populates="cross_examinations")
    batch = relationship("ExchangeBatch", back_populates="cross_examinations")
    examiner = relationship("User", back_populates="cross_examinations")


class EvidenceReview(Base):
    __tablename__ = "evidence_reviews"

    id = Column(Integer, primary_key=True, index=True)
    evidence_id = Column(Integer, ForeignKey("evidences.id"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(Enum(ReviewStatus), nullable=False, default=ReviewStatus.PENDING)
    format_ok = Column(Boolean)
    desensitization_ok = Column(Boolean)
    page_number_ok = Column(Boolean)
    comment = Column(Text)
    reviewed_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    evidence = relationship("Evidence", back_populates="reviews")
    reviewer = relationship("User", back_populates="reviews")


class SupplementaryMaterial(Base):
    __tablename__ = "supplementary_materials"

    id = Column(Integer, primary_key=True, index=True)
    evidence_id = Column(Integer, ForeignKey("evidences.id"), nullable=False)
    supplementary_evidence_id = Column(Integer, ForeignKey("evidences.id"), nullable=False)
    reason = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    evidence = relationship("Evidence", back_populates="supplements", foreign_keys=[evidence_id])
    supplementary_evidence = relationship("Evidence", back_populates="supplementary_of", foreign_keys=[supplementary_evidence_id])


class HearingCitation(Base):
    __tablename__ = "hearing_citations"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    evidence_id = Column(Integer, ForeignKey("evidences.id"), nullable=False)
    cited_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    page_reference = Column(String(200))
    dispute_focus = Column(Text)
    citation_content = Column(Text)
    cited_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("Case", back_populates="hearings")
    evidence = relationship("Evidence", back_populates="hearing_citations")
    cited_by = relationship("User", back_populates="hearings")


class ChunkUpload(Base):
    __tablename__ = "chunk_uploads"

    id = Column(Integer, primary_key=True, index=True)
    upload_id = Column(String(100), unique=True, nullable=False, index=True)
    file_name = Column(String(500), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    total_chunks = Column(Integer, nullable=False)
    uploaded_chunks = Column(Integer, default=0)
    chunk_size = Column(Integer, nullable=False)
    mime_type = Column(String(200))
    file_hash = Column(String(128))
    status = Column(Enum(UploadStatus), nullable=False, default=UploadStatus.PENDING)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
