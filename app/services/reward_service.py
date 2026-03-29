from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import RewardTransaction, VideoAsset, WalletAccount


def credit_reward_for_video(db: Session, video_id: str, reason: str = "FINAL_APPROVAL") -> RewardTransaction | None:
    existing = db.scalar(select(RewardTransaction).where(RewardTransaction.video_id == video_id, RewardTransaction.reason == reason))
    if existing:
        return existing

    video = db.scalar(select(VideoAsset).where(VideoAsset.video_id == video_id))
    if not video:
        return None

    wallet = db.scalar(select(WalletAccount).where(WalletAccount.uploader_ref == video.uploader_ref))
    if not wallet:
        wallet = WalletAccount(uploader_ref=video.uploader_ref, balance_points=0)
        db.add(wallet)
        db.flush()

    txn = RewardTransaction(
        uploader_ref=video.uploader_ref,
        video_id=video_id,
        points=settings.default_base_reward_points,
        reason=reason,
    )
    wallet.balance_points += txn.points
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn

