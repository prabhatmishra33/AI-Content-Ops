from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import AuditEvent
from app.core.security import require_roles
from app.schemas.common import ApiResponse


router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/{entity_type}/{entity_id}", response_model=ApiResponse)
def get_audit_events(entity_type: str, entity_id: str, _user=Depends(require_roles("admin", "moderator")), db: Session = Depends(get_db)):
    events = list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
            .order_by(AuditEvent.created_at.asc())
        )
    )
    return ApiResponse(
        data=[
            {
                "event_type": e.event_type,
                "actor_ref": e.actor_ref,
                "payload": e.payload,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]
    )
