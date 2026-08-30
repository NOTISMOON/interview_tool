"""E2E 辅助：列出所有 interviews 路由（调试用）。"""

from fastapi.testclient import TestClient

from app.main import app

_ = TestClient(app)
for r in app.routes:
    path = getattr(r, "path", "")
    if "interviews" in path:
        print(sorted(getattr(r, "methods", []) or []), path)
