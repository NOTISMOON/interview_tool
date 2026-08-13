"""认证相关Pydantic模型，定义GitHub OAuth登录的请求和响应结构。"""

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
    """登录令牌响应模型。"""

    access_token: str = Field(..., description="JWT访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    user: GitHubUserInfo = Field(..., description="用户信息")


class GitHubCallbackRequest(BaseModel):
    """GitHub OAuth回调请求模型。"""

    code: str = Field(..., description="GitHub授权回调返回的code参数")
    state: str | None = Field(default=None, description="防CSRF攻击的state参数")