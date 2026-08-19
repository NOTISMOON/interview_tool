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

    # RabbitMQ配置（aio-pika 异步客户端，用于MQ中间件）
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672//"
    RABBITMQ_PREFETCH_COUNT: int = 8  # 消费者预取数量，控制并发与背压

    # JWT配置
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Refresh Token配置
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # refresh token有效期（天）
    REFRESH_TOKEN_BYTES: int = 32  # refresh token随机字节数（32字节=256位）

    # 用户资料缓存配置（Cache-Aside，单位秒，默认30分钟）
    USER_PROFILE_CACHE_TTL: int = 1800

    # 关注关系缓存配置（ZSET分页 + SET关系判断）
    FOLLOW_CACHE_TTL: int = 86400  # ZSET/SET缓存有效期（秒，默认1天）
    FOLLOW_ZSET_REBUILD_LIMIT: int = 1000  # ZSET回源时加载的最近关注记录条数（超出部分读时降级查DB）
    FOLLOW_EMPTY_MARK_TTL: int = 60  # 空关注列表防穿透标记有效期（秒）

    # ---- Outbox 事件投递配置（关注/取关写路径，Transactional Outbox + RabbitMQ） ----
    OUTBOX_POLL_INTERVAL: float = 0.5  # Relay轮询间隔（秒）
    OUTBOX_BATCH_SIZE: int = 100  # 单批扫描与投递条数
    OUTBOX_MAX_RETRY: int = 5  # 投递最大重试次数，超限置死信
    OUTBOX_RETRY_BASE_DELAY: int = 5  # 重试退避基数（秒），实际延迟=base*2^retry_count
    OUTBOX_RETENTION_DAYS: int = 7  # 已发布事件保留天数，清理任务超期删除
    OUTBOX_CLEANUP_BATCH: int = 5000  # 清理任务单批DELETE上限
    OUTBOX_DEACTIVATED_PAYLOAD_LIMIT: int = 50000  # 注销事件payload中ID列表截断上限

    # Cookie与CORS配置（HttpOnly Cookie方案，token不下发前端JS）
    COOKIE_SECURE: bool = False  # 是否仅HTTPS传输，生产环境必须为True
    COOKIE_SAMESITE: str = "lax"  # SameSite策略：lax兼顾CSRF防护与OAuth跳转体验
    COOKIE_DOMAIN: str | None = None  # Cookie作用域名，None表示当前域
    COOKIE_ACCESS_PATH: str = "/"  # access_token Cookie路径（全部API可用）
    COOKIE_REFRESH_PATH: str = "/api/v1/auth"  # refresh_token Cookie路径（仅认证端点发送，缩小暴露面）
    CORS_ORIGINS: list[str] = ["http://localhost:5645"]  # 前端跨域白名单，credentials=True时禁止通配符

    # ---- SSE 配置 ----
    SSE_KEEPALIVE_INTERVAL: int = 15  # 心跳注释帧间隔（秒），防Nginx/CDN超时断
    SSE_RETRY_INTERVAL_MS: int = 3000  # 服务端建议浏览器断线重连间隔（毫秒）
    SSE_CATCHUP_LIMIT: int = 10  # 建立/重连SSE时的增量补偿上限（固定最多10条）

    # ---- Redis Pub/Sub 通道 ----
    NOTIFY_PUSH_CHANNEL_PREFIX: str = "notify:push"  # notify:push:{user_id}
    NOTIFY_BROADCAST_CHANNEL: str = "notify:broadcast"  # 系统公告通道

    # ---- 通知业务 ----
    NOTIFICATION_LIKE_COMBINE_WINDOW_SECONDS: int = 86400  # 点赞合并窗口：24h同一人多次点赞只1条通知
    # GitHub OAuth配置
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_REDIRECT_URI: str = "http://localhost:5645/callback"

    # ---- 腾讯云 COS 配置（前端直传 + 后端校验） ----
    COS_SECRET_ID: str = ""  # 腾讯云永久SecretId（仅后端使用）
    COS_SECRET_KEY: str = ""  # 腾讯云永久SecretKey（仅后端使用，切勿暴露给前端）
    COS_BUCKET: str = "test-1381433578"  # COS Bucket名称（含APPID）
    COS_REGION: str = "ap-chengdu"  # COS地域
    COS_STS_DURATION: int = 1800  # STS临时密钥有效期（秒，默认30分钟）
    COS_MAX_FILE_SIZE: int = 10485760  # 上传文件大小上限（字节，默认10MB）
    COS_ALLOWED_EXTENSIONS: str = ".pdf,.doc,.docx,.png,.jpg,.jpeg"  # 允许的扩展名白名单
    COS_DAILY_UPLOAD_LIMIT: int = 20  # 单用户每日上传次数上限
    model_config = {
        "env_file": str(Path(__file__).resolve().parent.parent.parent / ".env"),
        "env_file_encoding": "utf-8",
    }


settings = Settings()