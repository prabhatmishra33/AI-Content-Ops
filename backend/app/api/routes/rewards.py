from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import RewardTransaction, WalletAccount
from app.core.security import require_roles
from app.schemas.common import ApiResponse


router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("/admin/overview", response_model=ApiResponse)
def get_admin_wallet_overview(_user=Depends(require_roles("admin")), db: Session = Depends(get_db)):
    txn_rows = list(
        db.execute(
            select(
                RewardTransaction.uploader_ref,
                func.coalesce(func.sum(RewardTransaction.points), 0).label("total_points"),
                func.count(RewardTransaction.id).label("reward_count"),
                func.max(RewardTransaction.created_at).label("last_reward_at"),
            )
            .group_by(RewardTransaction.uploader_ref)
            .order_by(func.max(RewardTransaction.created_at).desc())
        )
    )

    txns = list(db.scalars(select(RewardTransaction).order_by(RewardTransaction.created_at.desc())))
    txns_by_user: dict[str, list[dict]] = {}
    for t in txns:
        txns_by_user.setdefault(t.uploader_ref, []).append(
            {
                "video_id": t.video_id,
                "points": t.points,
                "reason": t.reason,
                "created_at": t.created_at.isoformat(),
            }
        )

    users = []
    for row in txn_rows:
        users.append(
            {
                "uploader_ref": row.uploader_ref,
                "balance_points": int(row.total_points or 0),
                "reward_count": int(row.reward_count or 0),
                "last_reward_at": row.last_reward_at.isoformat() if row.last_reward_at else None,
                "transactions": txns_by_user.get(row.uploader_ref, []),
            }
        )

    total_points = sum(u["balance_points"] for u in users)
    total_rewarded_users = len(users)
    return ApiResponse(
        data={
            "total_rewarded_users": total_rewarded_users,
            "total_points_issued": total_points,
            "users": users,
        }
    )


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
