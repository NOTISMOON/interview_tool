"""认证相关API端点，处理GitHub OAuth登录与JWT令牌签发。"""

from fastapi import APIRouter, HTTPException, status

from app.schemas.auth import GitHubCallbackRequest, TokenResponse
from app.services.github_oauth_service import github_oauth_service
from app.core.security import create_access_token

router = APIRouter(prefix="/auth", tags=["认证"])


@router.get("/github/login", summary="获取GitHub OAuth授权URL")
async def github_login() -> dict:
    """返回GitHub OAuth授权页面URL，前端需将用户重定向到该URL。

    Returns:
        包含授权URL的字典。
    """
    url = github_oauth_service.get_authorize_url()
    return {"authorize_url": url}


@router.post("/github/callback", response_model=TokenResponse, summary="GitHub OAuth回调处理")
async def github_callback(request: GitHubCallbackRequest) -> TokenResponse:
    """处理GitHub OAuth回调，用授权码换取令牌并签发JWT。

    Args:
        request: 包含GitHub回调code参数的请求体。

    Returns:
        TokenResponse: 包含JWT令牌和用户信息。

    Raises:
        HTTPException: GitHub认证失败时抛出。
    """
    user_info, _ = await github_oauth_service.authenticate(request.code)

    # 以GitHub用户信息生成JWT载荷
    token_payload = {
        "sub": str(user_info.id),
        "login": user_info.login,
        "name": user_info.name,
        "avatar_url": user_info.avatar_url,
    }
    access_token = create_access_token(token_payload)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=user_info,
    )