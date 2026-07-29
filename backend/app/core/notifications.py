from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


def notify(db: AsyncSession, user_id: int, notification_type: str, message: str, link: str | None = None) -> None:
    """Queues a notification on the given session -- relies on the caller's
    existing commit() to persist it alongside whatever triggered it, so a
    notification never appears for a state change that itself rolled back."""
    db.add(Notification(user_id=user_id, type=notification_type, message=message, link=link))
