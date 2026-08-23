"""热门帖子服务回归测试。

覆盖核心热度计算逻辑，重点回归验证：
  - 超过 7 天窗口的历史热门帖子（is_hot=1）在重新计算后必须被清除，
    避免"最热僵尸"（旧帖子 is_hot 永不重置）长期霸榜。

用法: 在 api_server 目录下用 interview 环境运行
    python -m pytest tests/test_hot_post.py -v
"""

from datetime import datetime, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.post import POST_STATUS_NORMAL, Post
from app.services import hot_post_service as hps_module
from app.services.hot_post_service import HotPostService

# SQLite 兼容的 post 建表语句（移除 MySQL 专有 ON UPDATE 子句，JSON 用 TEXT 表示）
_POST_DDL = """
CREATE TABLE post (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    cover_url VARCHAR(512),
    images TEXT,
    tags TEXT,
    likes_count INTEGER NOT NULL DEFAULT 0,
    comments_count INTEGER NOT NULL DEFAULT 0,
    views_count INTEGER NOT NULL DEFAULT 0,
    is_pinned INTEGER NOT NULL DEFAULT 0,
    is_hot INTEGER NOT NULL DEFAULT 0,
    status INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


class ZSetFakeRedis:
    """内存版 Redis 桩，支持热门服务用到的 ZSET/流水线接口。"""

    def __init__(self) -> None:
        """初始化内存存储结构。"""
        self.zsets: dict[str, dict[str, float]] = {}

    def pipeline(self) -> "ZSetFakeRedis":
        """返回自身作为流水线对象（无需真正批量执行）。"""
        return self

    def delete(self, *keys: str) -> None:
        """删除指定键。"""
        for key in keys:
            self.zsets.pop(key, None)

    def zadd(self, key: str, mapping: dict) -> None:
        """向有序集合写入成员与分数。"""
        self.zsets.setdefault(key, {}).update({str(m): float(s) for m, s in mapping.items()})

    def expire(self, key: str, seconds: int) -> bool:
        """TTL 设置（仅记录，不实现过期）。"""
        return True

    def execute(self) -> None:
        """流水线执行（无实际行为）。"""
        return None


def _make_session() -> object:
    """构造带 post 表的内存 SQLite 会话。

    Returns:
        配置好的 SQLAlchemy Session。
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text(_POST_DDL))
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return factory()


def test_calc_hot_clears_stale_is_hot_older_than_7days(monkeypatch) -> None:
    """回归：超过 7 天窗口的旧热门帖子在重新计算后被清除 is_hot。"""
    db = _make_session()
    try:
        now = datetime.now()
        # 旧帖子：8 天前发布，历史被判为热门（最热僵尸，应被清除）
        db.add(
            Post(
                id=1,
                author_id=1,
                title="old",
                content="old content",
                likes_count=5,
                comments_count=2,
                views_count=100,
                is_hot=1,
                status=POST_STATUS_NORMAL,
                created_at=now - timedelta(days=8),
            )
        )
        # 新帖子：1 天前发布，点赞多，应成为热门
        db.add(
            Post(
                id=2,
                author_id=2,
                title="new",
                content="new content",
                likes_count=100,
                comments_count=10,
                views_count=1000,
                is_hot=0,
                status=POST_STATUS_NORMAL,
                created_at=now - timedelta(days=1),
            )
        )
        db.commit()

        # 用测试会话替换 SyncSessionLocal，并注入内存 Redis
        monkeypatch.setattr(hps_module, "SyncSessionLocal", lambda: db)
        svc = HotPostService(cache_client=ZSetFakeRedis())

        svc.calc_hot_posts()

        # 断言：超过 7 天的旧热门帖子 is_hot 被清除为 0
        old = db.get(Post, 1)
        assert old.is_hot == 0, "超过 7 天窗口的旧热门帖子应被清除 is_hot"
        # 断言：近 7 天的高热度帖子被标记为热门
        new = db.get(Post, 2)
        assert new.is_hot == 1, "近 7 天的高热度帖子应被标记为热门"
    finally:
        db.close()


def test_calc_hot_with_no_recent_posts_clears_all_is_hot(monkeypatch) -> None:
    """回归：近 7 天无帖子时，历史热门标记也应被全部清除。"""
    db = _make_session()
    try:
        now = datetime.now()
        # 仅一条 8 天前发布的历史热门帖子，近 7 天无任何帖子
        db.add(
            Post(
                id=1,
                author_id=1,
                title="old",
                content="old content",
                likes_count=0,
                comments_count=0,
                views_count=0,
                is_hot=1,
                status=POST_STATUS_NORMAL,
                created_at=now - timedelta(days=8),
            )
        )
        db.commit()

        monkeypatch.setattr(hps_module, "SyncSessionLocal", lambda: db)
        svc = HotPostService(cache_client=ZSetFakeRedis())

        svc.calc_hot_posts()

        old = db.get(Post, 1)
        assert old.is_hot == 0, "近 7 天无帖子时，历史热门标记应被清除"
    finally:
        db.close()


def test_calc_hot_ignores_negative_score_posts(monkeypatch) -> None:
    """回归：热度分为负的帖子即使近 7 天也不应被标记为热门（避免矮子里拔将军）。"""
    db = _make_session()
    try:
        now = datetime.now()
        # 低热度帖子：5 天前发布，无任何互动，时间衰减后热度分为负
        db.add(
            Post(
                id=1,
                author_id=1,
                title="cold",
                content="cold content",
                likes_count=0,
                comments_count=0,
                views_count=0,
                is_hot=1,
                status=POST_STATUS_NORMAL,
                created_at=now - timedelta(days=5),
            )
        )
        # 高热度帖子：1 天前发布，点赞多，热度分为正
        db.add(
            Post(
                id=2,
                author_id=2,
                title="hot",
                content="hot content",
                likes_count=50,
                comments_count=5,
                views_count=200,
                is_hot=0,
                status=POST_STATUS_NORMAL,
                created_at=now - timedelta(days=1),
            )
        )
        db.commit()

        fake_redis = ZSetFakeRedis()
        monkeypatch.setattr(hps_module, "SyncSessionLocal", lambda: db)
        svc = HotPostService(cache_client=fake_redis)

        svc.calc_hot_posts()

        cold = db.get(Post, 1)
        hot = db.get(Post, 2)
        assert cold.is_hot == 0, "负分帖子不应被标记为热门"
        assert hot.is_hot == 1, "正分帖子应被标记为热门"
        # Redis ZSET 应只包含正分帖子
        zset_members = set(fake_redis.zsets.get(hps_module.HOT_ZSET_KEY, {}).keys())
        assert zset_members == {"2"}, "Redis ZSET 应只包含正分帖子"
    finally:
        db.close()
