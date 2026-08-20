"""ORM模型包，统一导出所有模型。"""

from app.db.base import Base
from app.models.comment import Comment
from app.models.dm_conversation import DmConversation
from app.models.dm_message import DmMessage
from app.models.interview import Interview
from app.models.interview_question import InterviewQuestion
from app.models.interview_report import InterviewReport
from app.models.message import Message
from app.models.outbox_event import OutboxEvent
from app.models.post import Post
from app.models.post_favorite import PostFavorite
from app.models.post_like import PostLike
from app.models.post_tag import PostTag
from app.models.resume import Resume
from app.models.resume_work_experience import ResumeWorkExperience
from app.models.upload_record import UploadRecord
from app.models.user import User
from app.models.user_activity import UserActivity
from app.models.user_auth import UserAuth
from app.models.user_follow import UserFollow
from app.models.user_settings import UserSettings

__all__ = [
    "Base",
    "Comment",
    "DmConversation",
    "DmMessage",
    "Interview",
    "InterviewQuestion",
    "InterviewReport",
    "Message",
    "OutboxEvent",
    "Post",
    "PostFavorite",
    "PostLike",
    "PostTag",
    "Resume",
    "ResumeWorkExperience",
    "UploadRecord",
    "User",
    "UserActivity",
    "UserAuth",
    "UserFollow",
    "UserSettings",
]