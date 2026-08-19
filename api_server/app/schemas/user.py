"""用户模块Pydantic模型，定义用户管理接口的请求/响应体。"""

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


class UserUpdateRequest(BaseModel):
    """更新个人资料请求模型（所有字段可选，仅更新提交的字段）。"""

    nickname: str | None = Field(None, min_length=1, max_length=64, description="用户昵称")
    avatar: str | None = Field(None, description="头像URL")
    gender: int | None = Field(None, ge=0, le=2, description="性别 0-未设置 1-男 2-女")
    birthday: date | None = Field(None, description="生日")
    bio: str | None = Field(None, max_length=512, description="个人简介")
    phone: str | None = Field(None, max_length=32, description="手机号")
    location: str | None = Field(None, max_length=128, description="所在地")

    @model_validator(mode="after")
    def check_not_empty(self) -> "UserUpdateRequest":
        """校验请求至少包含一个待更新字段，避免空更新。"""
        if not any(
            getattr(self, field) is not None
            for field in ("nickname", "avatar", "gender", "birthday", "bio", "phone", "location")
        ):
            raise ValueError("至少需要提供一个待更新字段")
        return self


class ProfileVisibilityUpdateRequest(BaseModel):
    """更新资料可见性请求模型（按字段分别设置可见性，对应user_settings表）。"""

    visibility_gender: int | None = Field(None, ge=0, le=1, description="性别可见 0-不可见 1-可见")
    visibility_birthday: int | None = Field(None, ge=0, le=1, description="生日可见")
    visibility_bio: int | None = Field(None, ge=0, le=1, description="简介可见")
    visibility_location: int | None = Field(None, ge=0, le=1, description="所在地可见")
    visibility_phone: int | None = Field(None, ge=0, le=1, description="手机号可见")


class UserSettingsResponse(BaseModel):
    """用户设置响应模型。"""

    model_config = {"from_attributes": True}

    email_notify: int
    push_notify: int
    sound_enabled: int
    public_profile: int
    visibility_gender: int
    visibility_birthday: int
    visibility_bio: int
    visibility_location: int
    visibility_phone: int


class UserProfileResponse(BaseModel):
    """个人信息响应模型（仅本人可见，含敏感字段）。"""

    model_config = {"from_attributes": True}

    id: int
    email: str | None
    nickname: str
    avatar: str | None
    gender: int
    birthday: date | None
    bio: str
    phone: str | None
    location: str | None
    profile_visibility: int
    visibility_gender: int = Field(1, description="性别可见 0-不可见 1-可见（来自user_settings表）")
    visibility_birthday: int = Field(1, description="生日可见")
    visibility_bio: int = Field(1, description="简介可见")
    visibility_location: int = Field(1, description="所在地可见")
    visibility_phone: int = Field(0, description="手机号可见")
    following_count: int
    followers_count: int
    posts_count: int
    created_at: datetime
    updated_at: datetime


class UserPublicProfileResponse(BaseModel):
    """他人公开资料响应模型（不含邮箱、手机等敏感字段）。"""

    model_config = {"from_attributes": True}

    id: int
    nickname: str
    avatar: str | None
    bio: str
    location: str | None
    following_count: int
    followers_count: int
    posts_count: int
    created_at: datetime


class UserCardResponse(BaseModel):
    """受限用户卡片响应模型（仅关注者可见的用户对非关注者返回）。"""

    model_config = {"from_attributes": True}

    id: int
    nickname: str
    avatar: str | None


class FollowItemResponse(BaseModel):
    """关注/粉丝列表项响应模型（由ZSET分页 + user表批量详情组装）。"""

    id: int = Field(..., description="用户ID（关注列表为被关注者，粉丝列表为关注者）")
    nickname: str = Field(..., description="昵称")
    avatar: str | None = Field(None, description="头像URL")
    bio: str = Field("", description="个人简介")
    location: str | None = Field(None, description="所在地")
    followed_at: datetime = Field(..., description="关注时间（ZSET score还原或DB降级查询所得）")
    is_following: bool = Field(False, description="当前访问者是否关注了该用户")
    is_mutual: bool = Field(False, description="是否与当前访问者互相关注")


class FollowListResponse(BaseModel):
    """关注/粉丝列表分页响应模型（游标分页）。"""

    items: list[FollowItemResponse] = Field(default_factory=list, description="本页列表项")
    next_cursor: int | None = Field(
        None,
        description="下一页游标（上一页最后一条的followed_at毫秒时间戳），为空表示没有更多数据",
    )
    following_count: int = Field(0, description="列表属主的关注数")
    followers_count: int = Field(0, description="列表属主的粉丝数")
    restricted: bool = Field(
        False,
        description="列表是否受可见性限制（属主开启'仅关注者可见'且访问者未关注时为True，此时items为空）",
    )