"""评论模块Pydantic模型，定义评论管理接口的请求/响应体。"""

from datetime import datetime

from pydantic import BaseModel, Field


class CommentCreate(BaseModel):
    """创建评论请求模型。

    一级评论: root_id=None, reply_user_id=None
    回复评论: root_id=一级评论ID, reply_user_id=被回复者ID
    """

    post_id: int | None = Field(None, ge=1, description="所属帖子ID（以路径参数为准，body可不传）")
    content: str = Field(..., min_length=1, max_length=1000, description="评论内容")
    root_id: int | None = Field(None, ge=1, description="根评论ID（回复时传一级评论ID）")
    reply_user_id: int | None = Field(None, ge=1, description="被回复者用户ID（回复时传）")


class CommentAuthor(BaseModel):
    """评论作者信息（嵌套在评论响应中）。"""

    id: int = Field(..., description="作者用户ID")
    nickname: str = Field(..., description="作者昵称")
    avatar: str | None = Field(None, description="作者头像URL")


class CommentResponse(BaseModel):
    """评论响应模型。"""

    model_config = {"from_attributes": True}

    id: int
    post_id: int
    root_id: int | None = Field(None, description="根评论ID（NULL=一级评论）")
    author: CommentAuthor | None = Field(None, description="评论者信息（由Service层组装）")
    reply_to: CommentAuthor | None = Field(None, description="被回复者信息（由Service层组装，NULL=一级评论）")
    content: str
    likes_count: int = Field(0, description="点赞数")
    reply_count: int = Field(0, description="回复数（仅一级评论维护）")
    is_liked: bool = Field(False, description="当前用户是否已点赞")
    created_at: datetime
    updated_at: datetime


class CommentListResponse(BaseModel):
    """评论列表分页响应模型（游标分页）。"""

    items: list[CommentResponse] = Field(default_factory=list, description="本页评论列表")
    next_cursor: int | None = Field(
        None,
        description="下一页游标（上一页最后一条评论ID），为空表示没有更多数据",
    )
    total: int = Field(0, description="评论总数")