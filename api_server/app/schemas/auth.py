"""认证相关Pydantic模型，定义GitHub OAuth登录、Token刷新与退出的请求和响应结构。"""

from pydantic import BaseModel, Field


class GitHubUserInfo(BaseModel):
    """GitHub用户信息模型。"""

    id: int = Field(..., description="GitHub用户唯一ID")
    login: str = Field(..., description="GitHub用户名")
    name: str | None = Field(default=None, description="用户显示名称")
    email: str | None = Field(default=None, description="用户邮箱")
    avatar_url: str | None = Field(default=None, description="用户头像URL")
    html_url: str | None = Field(default=None, description="用户GitHub主页URL")


class TokenResponse(BaseModel):
    """登录令牌响应模型（双Token通过HttpOnly Cookie下发，响应体仅返回user和jti）。"""

    user: GitHubUserInfo = Field(..., description="用户信息")
    jti: str | None = Field(default=None, description="当前会话的JTI，用于前端过滤自身session_kicked事件")


class RefreshResponse(BaseModel):
    """刷新Token响应模型（轮转后的新Token对通过Cookie下发，响应体无敏感数据）。"""

    token_type: str = Field(default="bearer", description="令牌类型")


class GitHubCallbackRequest(BaseModel):
    """GitHub OAuth回调请求模型。"""

    code: str = Field(..., description="GitHub授权回调返回的code参数")
    state: str | None = Field(default=None, description="防CSRF攻击的state参数")
