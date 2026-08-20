"""ORM模型包，统一导出所有模型。"""

from app.db.base import Base
from app.models.comment import Comment
from app.models.message import Message
from app.models.outbox_event import OutboxEvent
from app.models.post import Post
from app.models.post_favorite import PostFavorite
from app.models.post_like import PostLike
from app.models.post_tag import PostTag
from app.models.upload_record import UploadRecord
from app.models.user import User
from app.models.user_activity import UserActivity
from app.models.user_auth import UserAuth
from app.models.user_follow import UserFollow

__all__ = [
    "Base",
    "Comment",
    "Message",
    "OutboxEvent",
    "Post",
    "PostFavorite",
    "PostLike",
    "PostTag",
    "UploadRecord",
    "User",
    "UserActivity",
    "UserAuth",
    "UserFollow",
]