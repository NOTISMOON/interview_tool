"""应用配置模块，从环境变量中读取配置。"""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置类，所有配置项从环境变量或 .env 文件加载。"""

    # 应用基础配置
    APP_NAME: str = "Interview Tool API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # 数据库配置
    MYSQL_URL: str = "mysql+pymysql://user:pass@localhost:3306/interview_db"
    MYSQL_ASYNC_URL: str = "mysql+aiomysql://user:pass@localhost:3306/interview_db"

    # Redis配置
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT配置
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Refresh Token配置
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # refresh token有效期（天）
    REFRESH_TOKEN_BYTES: int = 32  # refresh token随机字节数（32字节=256位）

    # Cookie与CORS配置（HttpOnly Cookie方案，token不下发前端JS）
    COOKIE_SECURE: bool = False  # 是否仅HTTPS传输，生产环境必须为True
    COOKIE_SAMESITE: str = "lax"  # SameSite策略：lax兼顾CSRF防护与OAuth跳转体验
    COOKIE_DOMAIN: str | None = None  # Cookie作用域名，None表示当前域
    COOKIE_ACCESS_PATH: str = "/"  # access_token Cookie路径（全部API可用）
    COOKIE_REFRESH_PATH: str = "/api/v1/auth"  # refresh_token Cookie路径（仅认证端点发送，缩小暴露面）
    CORS_ORIGINS: list[str] = ["http://localhost:5645"]  # 前端跨域白名单，credentials=True时禁止通配符

    # 前端路由配置（认证中间件长期Token失效时，后端302重定向到该登录页）
    FRONTEND_LOGIN_URL: str = "http://localhost:5645/login"

    # GitHub OAuth配置
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_REDIRECT_URI: str = "http://localhost:5645/callback" 
    model_config = {
        "env_file": str(Path(__file__).resolve().parent.parent.parent / ".env"),
        "env_file_encoding": "utf-8",
    }


settings = Settings()