from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_roles
from app.routers.parties import check_case_access
from datetime import datetime

router = APIRouter(prefix="/api/cases/{case_id}/catalogs", tags=["证据目录"])


def build_catalog_tree(catalogs: List[models.EvidenceCatalog], parent_id: Optional[int] = None) -> List[dict]:
    result = []
    for catalog in catalogs:
        if catalog.parent_id == parent_id:
            catalog_dict = {
                "id": catalog.id,
                "case_id": catalog.case_id,
                "name": catalog.name,
                "parent_id": catalog.parent_id,
                "order_index": catalog.order_index,
                "is_frozen": catalog.is_frozen,
                "frozen_at": catalog.frozen_at,
                "created_at": catalog.created_at,
                "updated_at": catalog.updated_at,
                "children": build_catalog_tree(catalogs, catalog.id)
            }
            result.append(catalog_dict)
    result.sort(key=lambda x: x["order_index"])
    return result


@router.post("", response_model=schemas.EvidenceCatalogResponse, status_code=status.HTTP_201_CREATED)
def create_catalog(
    case_id: int,
    catalog_data: schemas.EvidenceCatalogCreate,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN, models.UserRole.CLAIMANT, models.UserRole.RESPONDENT, models.UserRole.AGENT)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    if catalog_data.parent_id:
        parent = db.query(models.EvidenceCatalog).filter(
            models.EvidenceCatalog.id == catalog_data.parent_id,
            models.EvidenceCatalog.case_id == case_id
        ).first()
        if not parent:
            raise HTTPException(status_code=404, detail="父级目录不存在")
        if parent.is_frozen:
            raise HTTPException(status_code=400, detail="父级目录已冻结，无法添加子目录")

    db_catalog = models.EvidenceCatalog(
        case_id=case_id,
        **catalog_data.model_dump()
    )
    db.add(db_catalog)
    db.commit()
    db.refresh(db_catalog)
    return db_catalog


@router.get("", response_model=List[schemas.EvidenceCatalogResponse])
def list_catalogs(
    case_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    catalogs = db.query(models.EvidenceCatalog).filter(
        models.EvidenceCatalog.case_id == case_id
    ).order_by(models.EvidenceCatalog.order_index).all()

    tree = build_catalog_tree(catalogs)
    return tree


@router.get("/{catalog_id}", response_model=schemas.EvidenceCatalogResponse)
def get_catalog(
    case_id: int,
    catalog_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    catalog = db.query(models.EvidenceCatalog).filter(
        models.EvidenceCatalog.id == catalog_id,
        models.EvidenceCatalog.case_id == case_id
    ).first()
    if not catalog:
        raise HTTPException(status_code=404, detail="目录不存在")
    return catalog


@router.put("/{catalog_id}", response_model=schemas.EvidenceCatalogResponse)
def update_catalog(
    case_id: int,
    catalog_id: int,
    catalog_data: schemas.EvidenceCatalogUpdate,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    catalog = db.query(models.EvidenceCatalog).filter(
        models.EvidenceCatalog.id == catalog_id,
        models.EvidenceCatalog.case_id == case_id
    ).first()
    if not catalog:
        raise HTTPException(status_code=404, detail="目录不存在")

    if catalog.is_frozen:
        raise HTTPException(status_code=400, detail="目录已冻结，无法修改")

    if catalog_data.parent_id and catalog_data.parent_id != catalog.parent_id:
        parent = db.query(models.EvidenceCatalog).filter(
            models.EvidenceCatalog.id == catalog_data.parent_id,
            models.EvidenceCatalog.case_id == case_id
        ).first()
        if not parent:
            raise HTTPException(status_code=404, detail="父级目录不存在")

    update_data = catalog_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(catalog, key, value)

    db.commit()
    db.refresh(catalog)
    return catalog


@router.post("/{catalog_id}/freeze", response_model=schemas.EvidenceCatalogResponse)
def freeze_catalog(
    case_id: int,
    catalog_id: int,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    catalog = db.query(models.EvidenceCatalog).filter(
        models.EvidenceCatalog.id == catalog_id,
        models.EvidenceCatalog.case_id == case_id
    ).first()
    if not catalog:
        raise HTTPException(status_code=404, detail="目录不存在")

    catalog.is_frozen = True
    catalog.frozen_at = datetime.utcnow()
    catalog.frozen_by = current_user.id

    def freeze_children(parent_id: int):
        children = db.query(models.EvidenceCatalog).filter(
            models.EvidenceCatalog.parent_id == parent_id
        ).all()
        for child in children:
            child.is_frozen = True
            child.frozen_at = datetime.utcnow()
            child.frozen_by = current_user.id
            freeze_children(child.id)

    freeze_children(catalog.id)
    db.commit()
    db.refresh(catalog)
    return catalog


@router.post("/{catalog_id}/unfreeze", response_model=schemas.EvidenceCatalogResponse)
def unfreeze_catalog(
    case_id: int,
    catalog_id: int,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    catalog = db.query(models.EvidenceCatalog).filter(
        models.EvidenceCatalog.id == catalog_id,
        models.EvidenceCatalog.case_id == case_id
    ).first()
    if not catalog:
        raise HTTPException(status_code=404, detail="目录不存在")

    catalog.is_frozen = False
    catalog.frozen_at = None
    catalog.frozen_by = None

    def unfreeze_children(parent_id: int):
        children = db.query(models.EvidenceCatalog).filter(
            models.EvidenceCatalog.parent_id == parent_id
        ).all()
        for child in children:
            child.is_frozen = False
            child.frozen_at = None
            child.frozen_by = None
            unfreeze_children(child.id)

    unfreeze_children(catalog.id)
    db.commit()
    db.refresh(catalog)
    return catalog


@router.delete("/{catalog_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_catalog(
    case_id: int,
    catalog_id: int,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    catalog = db.query(models.EvidenceCatalog).filter(
        models.EvidenceCatalog.id == catalog_id,
        models.EvidenceCatalog.case_id == case_id
    ).first()
    if not catalog:
        raise HTTPException(status_code=404, detail="目录不存在")

    if catalog.is_frozen:
        raise HTTPException(status_code=400, detail="目录已冻结，无法删除")

    evidence_count = db.query(models.Evidence).filter(
        models.Evidence.catalog_id == catalog_id
    ).count()
    if evidence_count > 0:
        raise HTTPException(status_code=400, detail="目录下存在证据，无法删除")

    db.delete(catalog)
    db.commit()
