# Python 后端（FastAPI）开发规范 v1.0（面向AI代码生成Agent）

## 1. 文档目标

- **确保生成的后端代码**：语义正确、安全、高性能、易维护、符合FastAPI最佳实践。
- **适用技术栈**：Python 3.11+、FastAPI、SQLAlchemy 2.0（同步/异步）、Pydantic v2、MySQL、Redis。
- **Agent行动原则**：优先遵循现代Python与FastAPI最佳实践，避免过时或危险模式。
- **特别约定**：
  - **普通业务**（增删改查、简单查询）使用**同步客户端**操作 MySQL 和 Redis。
  - **Agent业务**（需要高并发、异步IO、多任务协作）使用**异步客户端**操作 MySQL 和 Redis。
  - **每个函数、方法、类都必须有简单的中文注释**（docstring或行内注释），说明用途、参数、返回值。

---

## 2. 通用规范（语言无关）

### 2.1 文件组织
- 一个文件对应一个模块/组件（如 `user_repository.py`、`agent_service.py`）。
- 项目采用分层架构，推荐目录结构：

```
app/
├── api/                     # API接口层（路由注册与版本管理）
│   ├── v1/
│   │   ├── controllers/     # 控制器层（路由处理函数）
│   │   │   ├── users.py
│   │   │   └── agent.py
│   │   └── __init__.py
│   └── deps.py              # 依赖注入接线板（不含业务逻辑）
├── core/                    # 核心配置（配置类、安全、日志）
│   ├── config.py
│   ├── security.py
│   └── logging.py
├── db/                      # 数据库连接与会话管理
│   ├── base.py              # ORM基类
│   ├── sync_session.py      # 同步会话
│   └── async_session.py     # 异步会话
├── redis/                   # Redis连接管理（与db平级）
│   ├── sync_client.py       # 同步Redis客户端
│   └── async_client.py      # 异步Redis客户端
├── models/                  # SQLAlchemy ORM模型
│   ├── user.py
│   └── agent_task.py
├── schemas/                 # Pydantic 模型（请求/响应）
│   ├── user.py
│   └── agent.py
├── services/                # 业务逻辑层
│   ├── user_service.py      # 普通业务（同步）
│   └── agent_service.py     # Agent业务（异步）
├── repositories/            # 数据访问层（Repository模式）
│   ├── user_repository.py   # 普通业务（同步）
│   └── agent_repository.py  # Agent业务（异步）
├── utils/                   # 纯通用工具函数（与业务无关）
└── main.py                  # FastAPI应用入口
```

- 测试文件与源代码同目录或专用 `tests/` 文件夹，命名以 `test_` 开头。

### 2.2 命名规范

| 类型 | 规则 | 示例 |
|------|------|------|
| Python文件 | 全小写，下划线分隔 | `user_repository.py` |
| 类名 | PascalCase | `UserRepository`, `AgentService` |
| 函数/方法名 | snake_case | `get_user_by_id`, `create_agent_task` |
| 变量名 | snake_case | `user_id`, `db_session` |
| 常量 | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT`, `DEFAULT_PAGE_SIZE` |
| 模块名 | 全小写，下划线分隔 | `user_service` |
| 私有属性/方法 | 前导下划线 `_` | `_validate_input` |
| 异常类 | PascalCase + `Error` 后缀 | `UserNotFoundError`, `DatabaseError` |

### 2.3 导入顺序
- 标准库导入 → 第三方库导入 → 本地应用导入，组间空一行。
- 示例：
```python
import os
from datetime import datetime

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.sync_session import get_db
from app.repositories.user_repository import UserRepository
```

### 2.4 缩进与换行
- 缩进：4个空格（禁止使用Tab）。
- 行宽：最大120字符。
- 文件末尾保留一个空行。
- 二元运算符换行时，运算符放在行首（PEP8推荐）。

### 2.5 注释要求（强制）
- **每个函数、方法、类必须有简单的中文注释**，采用 docstring 形式（类：描述职责；函数/方法：描述功能、参数、返回值、可能异常）。
- 复杂逻辑块内可添加行内注释，说明意图而非重复代码。
- 示例：
```python
def get_user_by_id(db: Session, user_id: int) -> User | None:
    """根据用户ID查询用户。

    Args:
        db: 数据库同步会话。
        user_id: 用户唯一标识。

    Returns:
        User对象，若不存在返回None。

    Raises:
        DatabaseError: 数据库查询失败时抛出。
    """
    ...
```

---

## 3. Python语言规范

### 3.1 语言特性
- 使用 Python 3.11+ 语法：类型注解、`dataclasses`、`asyncio`、上下文管理器。
- 优先使用 `pathlib` 处理路径，`f-string` 格式化字符串。
- 使用 `match` 语句（仅当逻辑清晰时）。
- 避免使用 `global`，不使用 `eval()`、`exec()`。
- 使用 `Enum` 定义枚举类型，提高可读性。

### 3.2 类型注解
- **所有公共函数、方法必须标注参数类型和返回值类型**。
- 使用 `typing` 模块：`Optional`、`Union`、`List`、`Dict`、`Any`（尽量避免`Any`）。
- 推荐使用 Python 3.10+ 新语法：`X | None` 代替 `Optional[X]`。
- 类属性必须使用 `ClassVar` 或实例属性注解。

```python
from typing import Annotated

def calculate_discount(price: float, discount_rate: float = 0.1) -> float:
    """计算折扣价格。"""
    return price * (1 - discount_rate)
```

### 3.3 异步编程
- **普通业务**：使用同步函数（`def`），方便调试与事务管理。
- **Agent业务**：使用异步函数（`async def`），避免阻塞事件循环。
- 异步函数中禁止调用同步阻塞IO（如 `time.sleep`、同步HTTP请求），应使用 `asyncio.to_thread` 或异步替代库。
- 使用 `asyncio.gather` 并发执行多个独立任务，注意异常处理。

### 3.4 异常处理
- 自定义业务异常继承 `Exception` 或 `HTTPException`。
- 捕获异常时明确异常类型，避免裸 `except:`。
- 使用 `finally` 释放资源。
- 日志记录异常堆栈，但不暴露内部细节给客户端。

```python
try:
    user = user_repo.get_by_id(db, user_id)
except DatabaseError:
    logger.exception("数据库查询用户失败")
    raise HTTPException(status_code=500, detail="服务器内部错误")
```

### 3.5 上下文管理器
- 管理资源（文件、数据库会话、Redis连接）必须使用 `with` 或 `async with`。

```python
with open("data.txt", "r") as f:
    content = f.read()
```

---

## 4. FastAPI框架规范

### 4.1 路由定义
- 路由文件按业务模块划分，使用 `APIRouter` 组织。
- 路径使用复数名词（如 `/users`、`/agent/tasks`），避免动词。
- HTTP方法语义正确：`GET`查询、`POST`创建、`PUT`全量更新、`PATCH`部分更新、`DELETE`删除。
- 路径参数、查询参数、请求体使用Pydantic模型定义。

```python
@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user_in: UserCreate, db: Session = Depends(get_db)) -> UserResponse:
    """创建新用户。"""
    ...
```

### 4.2 依赖注入
- 公共依赖（数据库会话、当前用户、权限校验）放在 `app/api/deps.py`。
- 使用 `Depends` 注入，避免全局变量。
- 数据库会话依赖根据业务类型提供同步或异步版本。

```python
# 同步依赖（普通业务）
def get_db() -> Generator[Session, None, None]:
    """获取数据库同步会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 异步依赖（Agent业务）
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库异步会话。"""
    async with AsyncSessionLocal() as session:
        yield session
```

### 4.3 请求/响应模型（Pydantic Schemas）
- 每个API必须有独立的Pydantic模型：`XxxCreate`、`XxxUpdate`、`XxxResponse`。
- 使用 `Field` 添加校验与示例：`Field(..., min_length=3, max_length=50, example="zhangsan")`。
- 响应模型排除敏感字段（密码哈希、内部ID可选）。
- 使用 `ConfigDict(from_attributes=True)` 支持ORM对象序列化。

```python
class UserCreate(BaseModel):
    """用户创建请求模型。"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
```

### 4.4 输入验证
- 依赖Pydantic自动校验，不在路由内手动校验。
- 自定义校验使用 `@field_validator` 或 `@model_validator`。
- 对路径参数和查询参数使用 `Path(..., ge=1)`、`Query(..., ge=1, le=100)` 限制。

```python
from pydantic import field_validator

class UserCreate(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """校验密码长度至少8位。"""
        if len(v) < 8:
            raise ValueError("密码长度至少8位")
        return v
```

### 4.5 异常处理
- 使用 `HTTPException` 返回标准HTTP错误，状态码准确。
- 可定义全局异常处理器（`@app.exception_handler`）统一错误响应格式。
- 业务异常映射到合适的HTTP状态码。

```python
class UserNotFoundException(Exception):
    """用户不存在异常。"""
    pass

@app.exception_handler(UserNotFoundException)
async def user_not_found_handler(request: Request, exc: UserNotFoundException):
    """处理用户不存在异常，返回404。"""
    return JSONResponse(status_code=404, content={"detail": "用户不存在"})
```

### 4.6 状态码
- 成功：200（查询）、201（创建）、204（删除，无返回体）。
- 客户端错误：400（参数错误）、401（未认证）、403（无权限）、404（资源不存在）、409（冲突）。
- 服务器错误：500（内部错误）、503（服务不可用）。

---

## 5. 数据库与Redis使用规范

### 5.1 技术栈约定
- ORM：SQLAlchemy 2.0。
- MySQL驱动：
  - 普通业务：`pymysql`（同步）。
  - Agent业务：`aiomysql`（异步）。
- Redis客户端：
  - 普通业务：`redis`（同步，`redis.Redis`）。
  - Agent业务：`redis.asyncio`（异步，`redis.asyncio.Redis`）。

### 5.2 数据库连接配置
- 统一在 `app/core/config.py` 使用 `pydantic-settings` 读取环境变量。
- 数据库URL与Redis URL从环境变量加载，禁止硬编码。

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """应用配置类，从环境变量读取。"""
    MYSQL_URL: str = "mysql+pymysql://user:pass@localhost:3306/db"
    MYSQL_ASYNC_URL: str = "mysql+aiomysql://user:pass@localhost:3306/db"
    REDIS_URL: str = "redis://localhost:6379/0"
    class Config:
        env_file = ".env"
```

### 5.3 普通业务：同步客户端（CRUD）
- 使用 `Session`（同步）进行增删改查，必须使用 `with` 或依赖注入管理会话。
- Repository 层封装数据访问，返回ORM对象或Pydantic模型。
- 事务：简单操作可直接提交，多步操作使用 `db.begin()` 或 `with db.begin():`。
- 禁止在循环内执行SQL查询（N+1问题），使用 `selectinload` 或 `joinedload` 预加载关联。

```python
class UserRepository:
    """用户数据访问层，负责用户CRUD操作（同步）。"""

    def get_by_id(self, db: Session, user_id: int) -> User | None:
        """根据ID查询用户。"""
        return db.get(User, user_id)

    def create(self, db: Session, user_in: UserCreate) -> User:
        """创建用户。"""
        user = User(**user_in.model_dump())
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
```

### 5.4 Agent业务：异步客户端
- 使用 `AsyncSession`（异步）和 `redis.asyncio.Redis`。
- Repository 方法定义为 `async def`，内部使用 `await`。
- 使用 `select` 查询时使用 `await session.execute(stmt)`。
- 事务使用 `async with session.begin():`。
- 避免在异步函数中调用同步数据库或Redis方法。

```python
class AgentTaskRepository:
    """Agent任务数据访问层（异步）。"""

    async def get_by_id(self, db: AsyncSession, task_id: int) -> AgentTask | None:
        """根据ID异步查询Agent任务。"""
        stmt = select(AgentTask).where(AgentTask.id == task_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
```

### 5.5 Redis客户端封装
- 提供同步客户端单例和异步客户端单例，避免频繁创建连接。
- 同步客户端：使用 `redis.Redis.from_url`。
- 异步客户端：使用 `redis.asyncio.Redis.from_url`，在应用启动/关闭时管理连接池。

```python
import redis.asyncio as aioredis

class RedisClient:
    """Redis客户端封装，提供同步与异步实例。"""
    _sync_client: redis.Redis | None = None
    _async_client: aioredis.Redis | None = None

    @classmethod
    def get_sync_client(cls) -> redis.Redis:
        """获取同步Redis客户端。"""
        if cls._sync_client is None:
            cls._sync_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return cls._sync_client

    @classmethod
    def get_async_client(cls) -> aioredis.Redis:
        """获取异步Redis客户端。"""
        if cls._async_client is None:
            cls._async_client = aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return cls._async_client
```

### 5.6 缓存策略
- 普通业务：使用同步Redis缓存热点数据（如用户信息），Cache-Aside模式（先查缓存，未命中查数据库并写缓存）。
- Agent业务：使用异步Redis进行任务队列、状态存储、分布式锁。
- 缓存键命名：`业务名:对象:ID`，如 `user:profile:123`，设置合理TTL。
- 序列化：使用 `json.dumps` / `json.loads` 或 `pickle`（注意安全）。

---

## 6. 安全规范

| 风险 | 禁止 | 要求 |
|------|------|------|
| SQL注入 | 拼接SQL字符串 | 使用ORM参数化查询，禁止原始SQL拼接 |
| 密码泄露 | 明文存储密码 | 使用 `passlib` + bcrypt/argon2 哈希密码 |
| JWT安全 | 硬编码密钥、过期时间过长 | 从环境变量读取密钥，设置合理过期时间（如30分钟） |
| CORS | 允许所有来源 | 配置 `CORSMiddleware` 白名单 |
| 敏感数据暴露 | 在日志中打印密码、token | 日志脱敏，响应模型排除敏感字段 |
| 越权访问 | 未校验资源归属 | 依赖注入中校验当前用户是否有权限 |
| CSRF | 基于Cookie的认证未防护 | 推荐使用Bearer Token，若用Cookie需CSRF Token |
| 依赖注入漏洞 | 信任客户端传来的ID | 始终从认证上下文获取用户ID，不信任请求体 |

- 所有用户输入必须经过Pydantic校验。
- 使用 `secrets` 模块生成随机令牌，不使用 `random`。
- 生产环境强制HTTPS，设置安全响应头（`SecurityHeadersMiddleware` 可选）。

### 6.1 认证与授权
- 使用 `python-jose` 实现JWT，包含 `sub`、`exp`、`iat` 字段。
- 依赖注入 `get_current_user` 解析并验证令牌。
- 权限控制可使用角色（`Depends(require_role("admin"))`）。

```python
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """从JWT令牌解析当前用户。"""
    payload = decode_token(token)
    user_id = payload.get("sub")
    user = user_repo.get_by_id(db, int(user_id))
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user
```

---

## 7. 性能与优化

- **数据库连接池**：同步使用 `QueuePool`，异步使用 `AsyncAdaptedQueuePool`，配置 `pool_size`、`max_overflow`。
- **查询优化**：
  - 禁止 `SELECT *`，显式指定列。
  - 使用 `selectinload` 避免N+1。
  - 分页使用 `limit`/`offset`，大数据量使用游标分页。
- **Redis**：使用连接池，设置合理超时，避免大Key。
- **异步处理**：耗时任务（发送邮件、文件处理）使用后台任务（FastAPI `BackgroundTasks`）或 Celery/RQ，不要在请求内阻塞。
- **响应压缩**：启用 GZip 中间件减少传输体积（可选）。
- **静态文件**：生产环境由Nginx托管，不通过FastAPI。

---

## 8. 日志与异常处理

- 使用 `logging` 标准库，配置统一格式。
- 日志级别：开发DEBUG，生产INFO。
- 日志中包含请求ID（中间件生成），方便追踪。
- 异常日志使用 `logger.exception`，自动记录堆栈。
- 不要在日志中记录密码、Token等敏感信息。

```python
import logging

logger = logging.getLogger(__name__)

def create_user(...):
    """创建用户。"""
    logger.info("创建用户: %s", user_in.username)
    try:
        ...
    except Exception as e:
        logger.exception("创建用户失败")
        raise
```

---

## 9. 测试规范

- 测试框架：`pytest` + `httpx`（FastAPI TestClient）。
- 每个API端点至少包含：
  - 正常请求测试。
  - 参数校验失败测试（400）。
  - 认证/权限失败测试（401/403）。
  - 数据库异常模拟测试。
- 使用 `pytest.fixture` 管理数据库会话和测试客户端。
- 测试命名：`test_函数名_场景_期望`，如 `test_create_user_with_valid_data_returns_201`。
- 每个测试函数必须有中文 docstring 说明测试目的。

```python
def test_create_user_success(client, db_session):
    """测试创建用户成功返回201。"""
    response = client.post("/api/v1/users", json={"username": "test", "password": "password123"})
    assert response.status_code == 201
    assert response.json()["username"] == "test"
```

---

## 10. 工具链与代码质量

- **代码格式化**：Black（`line-length = 120`）
- **导入排序**：isort（profile = black）
- **Linting**：Ruff（替代Flake8 + isort + pyupgrade）
- **类型检查**：Mypy（`strict = true`）
- **配置**：`pyproject.toml` 统一管理。
- **Pre-commit**：husky 等价（pre-commit）运行格式化、lint、测试。

```toml
[tool.black]
line-length = 120
target-version = ["py311"]

[tool.isort]
profile = "black"
line_length = 120

[tool.mypy]
strict = true
plugins = ["pydantic.mypy"]
```

---

## 11. 自检清单（Agent输出前必须验证）

- [ ] 每个函数、方法、类都有中文 docstring（含参数、返回值说明）。
- [ ] 所有公共函数/方法有类型注解。
- [ ] 普通业务使用同步数据库/Redis客户端，Agent业务使用异步客户端。
- [ ] 数据库会话通过依赖注入管理，无资源泄漏。
- [ ] 输入验证使用Pydantic模型，无手动类型转换。
- [ ] 密码已哈希存储，响应模型不包含敏感字段。
- [ ] SQL查询使用ORM参数化，无字符串拼接。
- [ ] 异步函数内未调用同步阻塞IO。
- [ ] 异常被捕获并记录日志，返回合适的HTTP状态码。
- [ ] 分页、过滤、排序参数有默认值和范围限制。
- [ ] 每个API端点至少有一个测试用例。
- [ ] 代码通过 Black、Ruff、Mypy 检查。
- [ ] 缓存键命名规范，设置TTL。
- [ ] 日志中不包含敏感信息。

---

## 12. 示例：完全符合规范的模块（普通业务同步 + Agent业务异步）

### 12.1 普通业务：用户管理（同步 CRUD）

#### models/user.py
```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

class User(Base):
    """用户ORM模型。"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
```

#### schemas/user.py
```python
from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    """用户创建请求模型。"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)

class UserResponse(BaseModel):
    """用户响应模型（不含密码）。"""
    id: int
    username: str
    email: EmailStr

    model_config = {"from_attributes": True}
```

#### repositories/user_repository.py
```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate

class UserRepository:
    """用户数据访问层，封装用户CRUD（同步）。"""

    def get_by_id(self, db: Session, user_id: int) -> User | None:
        """根据ID查询用户。"""
        return db.get(User, user_id)

    def get_by_username(self, db: Session, username: str) -> User | None:
        """根据用户名查询用户。"""
        stmt = select(User).where(User.username == username)
        return db.execute(stmt).scalar_one_or_none()

    def create(self, db: Session, user_in: UserCreate, hashed_password: str) -> User:
        """创建新用户。"""
        user = User(
            username=user_in.username,
            email=user_in.email,
            hashed_password=hashed_password,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
```

#### services/user_service.py
```python
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserResponse

class UserService:
    """用户业务逻辑层。"""

    def __init__(self) -> None:
        """初始化用户服务。"""
        self.repo = UserRepository()

    def create_user(self, db: Session, user_in: UserCreate) -> UserResponse:
        """创建用户并返回响应模型。"""
        hashed_password = get_password_hash(user_in.password)
        user = self.repo.create(db, user_in, hashed_password)
        return UserResponse.model_validate(user)
```

#### api/v1/controllers/users.py
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.user import UserCreate, UserResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user_in: UserCreate, db: Session = Depends(get_db)) -> UserResponse:
    """创建新用户（普通业务，同步）。"""
    service = UserService()
    try:
        return service.create_user(db, user_in)
    except Exception as e:
        raise HTTPException(status_code=500, detail="创建用户失败")
```

### 12.2 Agent业务：任务处理（异步 CRUD）

#### models/agent_task.py
```python
from sqlalchemy import String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

class AgentTask(Base):
    """Agent任务ORM模型。"""
    __tablename__ = "agent_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    prompt: Mapped[str] = mapped_column(Text)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
```

#### schemas/agent.py
```python
from pydantic import BaseModel

class AgentTaskCreate(BaseModel):
    """Agent任务创建请求模型。"""
    name: str
    prompt: str

class AgentTaskResponse(BaseModel):
    """Agent任务响应模型。"""
    id: int
    name: str
    prompt: str
    is_completed: bool

    model_config = {"from_attributes": True}
```

#### repositories/agent_repository.py
```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_task import AgentTask
from app.schemas.agent import AgentTaskCreate

class AgentTaskRepository:
    """Agent任务数据访问层（异步）。"""

    async def get_by_id(self, db: AsyncSession, task_id: int) -> AgentTask | None:
        """根据ID异步查询任务。"""
        stmt = select(AgentTask).where(AgentTask.id == task_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, db: AsyncSession, task_in: AgentTaskCreate) -> AgentTask:
        """异步创建任务。"""
        task = AgentTask(**task_in.model_dump())
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task
```

#### services/agent_service.py
```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_repository import AgentTaskRepository
from app.schemas.agent import AgentTaskCreate, AgentTaskResponse

class AgentService:
    """Agent业务逻辑层（异步）。"""

    def __init__(self) -> None:
        """初始化Agent服务。"""
        self.repo = AgentTaskRepository()

    async def create_task(self, db: AsyncSession, task_in: AgentTaskCreate) -> AgentTaskResponse:
        """异步创建Agent任务。"""
        task = await self.repo.create(db, task_in)
        return AgentTaskResponse.model_validate(task)
```

#### api/v1/controllers/agent.py
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_db
from app.schemas.agent import AgentTaskCreate, AgentTaskResponse
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agent/tasks", tags=["agent"])

@router.post("/", response_model=AgentTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_task(
    task_in: AgentTaskCreate,
    db: AsyncSession = Depends(get_async_db)
) -> AgentTaskResponse:
    """创建Agent任务（异步业务）。"""
    service = AgentService()
    try:
        return await service.create_task(db, task_in)
    except Exception as e:
        raise HTTPException(status_code=500, detail="创建任务失败")
```

---

**文档版本**：1.0  
**适用对象**：AI代码生成Agent  
**参考标准**：PEP 8、FastAPI官方文档、SQLAlchemy 2.0、OWASP API Security、12-Factor App