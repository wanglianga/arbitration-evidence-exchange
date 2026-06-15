from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_roles
from app.routers.parties import check_case_access

router = APIRouter(prefix="/api/cases/{case_id}/agents", tags=["案件代理人"])


@router.post("", response_model=schemas.AgentResponse, status_code=status.HTTP_201_CREATED)
def add_agent(
    case_id: int,
    agent_data: schemas.AgentCreate,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    user = db.query(models.User).filter(models.User.id == agent_data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    existing = db.query(models.Agent).filter(
        models.Agent.case_id == case_id,
        models.Agent.user_id == agent_data.user_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="该用户已作为代理人加入案件")

    db_agent = models.Agent(
        case_id=case_id,
        **agent_data.model_dump()
    )
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)
    return db_agent


@router.get("", response_model=List[schemas.AgentResponse])
def list_agents(
    case_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    agents = db.query(models.Agent).filter(
        models.Agent.case_id == case_id
    ).all()
    return agents


@router.put("/{agent_id}", response_model=schemas.AgentResponse)
def update_agent(
    case_id: int,
    agent_id: int,
    agent_data: schemas.AgentUpdate,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    agent = db.query(models.Agent).filter(
        models.Agent.id == agent_id,
        models.Agent.case_id == case_id
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="代理人不存在")

    update_data = agent_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(agent, key, value)

    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_agent(
    case_id: int,
    agent_id: int,
    current_user: models.User = Depends(require_roles(models.UserRole.SECRETARY, models.UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    check_case_access(case_id, current_user, db)

    agent = db.query(models.Agent).filter(
        models.Agent.id == agent_id,
        models.Agent.case_id == case_id
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="代理人不存在")

    db.delete(agent)
    db.commit()
