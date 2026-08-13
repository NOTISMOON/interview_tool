"""应用配置模块，从环境变量中读取配置。"""

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

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()