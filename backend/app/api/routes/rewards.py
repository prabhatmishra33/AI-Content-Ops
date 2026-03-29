from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import RewardTransaction, WalletAccount
from app.core.security import require_roles
from app.schemas.common import ApiResponse


router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("/{uploader_ref}", response_model=ApiResponse)
def get_wallet(uploader_ref: str, _user=Depends(require_roles("uploader", "admin", "moderator")), db: Session = Depends(get_db)):
    wallet = db.scalar(select(WalletAccount).where(WalletAccount.uploader_ref == uploader_ref))
    if not wallet:
        return ApiResponse(data={"uploader_ref": uploader_ref, "balance_points": 0})
    txns = list(
        db.scalars(
            select(RewardTransaction)
            .where(RewardTransaction.uploader_ref == uploader_ref)
            .order_by(RewardTransaction.created_at.desc())
        )
    )
    return ApiResponse(
        data={
            "uploader_ref": wallet.uploader_ref,
            "balance_points": wallet.balance_points,
            "transactions": [
                {
                    "video_id": t.video_id,
                    "points": t.points,
                    "reason": t.reason,
                    "created_at": t.created_at.isoformat(),
                }
                for t in txns
            ],
        }
    )
