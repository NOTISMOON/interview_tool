"""ORM模型包，统一导出所有模型。"""

from app.db.base import Base
from app.models.message import Message
from app.models.outbox_event import OutboxEvent
from app.models.upload_record import UploadRecord
from app.models.user import User
from app.models.user_activity import UserActivity
from app.models.user_auth import UserAuth
from app.models.user_follow import UserFollow

__all__ = [
    "Base",
    "Message",
    "OutboxEvent",
    "UploadRecord",
    "User",
    "UserActivity",
    "UserAuth",
    "UserFollow",
]