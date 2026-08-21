"""帖子模块Pydantic模型，定义帖子管理接口的请求/响应体。"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

# 标签数量上限
MAX_TAGS_COUNT = 5


class PostCreate(BaseModel):
    """创建帖子请求模型。"""

    title: str = Field(..., min_length=1, max_length=255, description="帖子标题")
    content: str = Field(..., min_length=1, description="帖子正文")
    cover_url: str | None = Field(None, max_length=512, description="封面图COS URL（先通过上传接口获取）")
    images: list[str] = Field(default_factory=list, max_length=9, description="帖子图片COS URL列表，最多9张")
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS_COUNT, description="标签列表，最多5个")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """校验每个标签不为空且去重。"""
        cleaned = [t.strip() for t in v if t.strip()]
        if len(cleaned) > MAX_TAGS_COUNT:
            raise ValueError(f"标签数量不能超过{MAX_TAGS_COUNT}个")
        return list(dict.fromkeys(cleaned))  # 去重保持顺序


class PostUpdate(BaseModel):
    """更新帖子请求模型（所有字段可选，仅更新提交的字段）。"""

    title: str | None = Field(None, min_length=1, max_length=255, description="帖子标题")
    content: str | None = Field(None, min_length=1, description="帖子正文")
    cover_url: str | None = Field(None, max_length=512, description="封面图COS URL")
    images: list[str] | None = Field(None, max_length=9, description="帖子图片COS URL列表，最多9张")
    tags: list[str] | None = Field(None, max_length=MAX_TAGS_COUNT, description="标签列表")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str] | None) -> list[str] | None:
        """校验每个标签不为空且去重。"""
        if v is None:
            return v
        cleaned = [t.strip() for t in v if t.strip()]
        if len(cleaned) > MAX_TAGS_COUNT:
            raise ValueError(f"标签数量不能超过{MAX_TAGS_COUNT}个")
        return list(dict.fromkeys(cleaned))

    @model_validator(mode="after")
    def check_not_empty(self) -> "PostUpdate":
        """校验请求至少包含一个待更新字段，避免空更新。"""
        if self.title is None and self.content is None and self.tags is None and self.cover_url is None and self.images is None:
            raise ValueError("至少需要提供一个待更新字段")
        return self


class PostAuthor(BaseModel):
    """帖子作者信息（嵌套在帖子响应中，避免前端二次请求）。"""

    id: int = Field(..., description="作者用户ID")
    nickname: str = Field(..., description="作者昵称")
    avatar: str | None = Field(None, description="作者头像URL")


class PostResponse(BaseModel):
    """帖子详情响应模型。"""

    model_config = {"from_attributes": True}

    id: int
    author: PostAuthor | None = Field(None, description="作者信息（由Service层组装）")
    title: str
    content: str
    cover_url: str | None = Field(None, description="封面图COS URL")
    images: list[str] = Field(default_factory=list, description="帖子图片COS URL列表")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    likes_count: int = Field(0, description="点赞数")
    comments_count: int = Field(0, description="评论数")
    views_count: int = Field(0, description="浏览数")
    is_hot: bool = Field(False, description="是否热门")
    is_liked: bool = Field(False, description="当前用户是否已点赞（由Service层组装，游客为False）")
    is_favorited: bool = Field(False, description="当前用户是否已收藏（由Service层组装，游客为False）")
    created_at: datetime
    updated_at: datetime


class PostListItem(BaseModel):
    """帖子列表项响应模型（比详情精简，不含正文全文）。"""

    id: int
    author: PostAuthor | None = Field(None, description="作者信息")
    title: str
    content_preview: str = Field("", description="正文摘要（前200字）")
    cover_url: str | None = Field(None, description="封面图COS URL")
    images_count: int = Field(0, description="图片数量")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    likes_count: int = Field(0, description="点赞数")
    comments_count: int = Field(0, description="评论数")
    views_count: int = Field(0, description="浏览数")
    is_hot: bool = Field(False, description="是否热门")
    is_liked: bool = Field(False, description="当前用户是否已点赞")
    is_favorited: bool = Field(False, description="当前用户是否已收藏")
    created_at: datetime


class PostListResponse(BaseModel):
    """帖子列表分页响应模型（游标分页）。"""

    items: list[PostListItem] = Field(default_factory=list, description="本页帖子列表")
    next_cursor: int | None = Field(
        None,
        description="下一页游标（上一页最后一条的帖子ID），为空表示没有更多数据",
    )
    total: int = Field(0, description="符合条件的帖子总数（可选，用于展示'共N条'）")