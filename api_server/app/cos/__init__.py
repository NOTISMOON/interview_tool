"""COS 客户端包，对外导出单例与工具函数。"""

from app.cos.cos import (
    CosClient,
    CosError,
    build_cos_url,
    cos_client,
    format_upload_date,
)

__all__ = ["CosClient", "CosError", "build_cos_url", "cos_client", "format_upload_date"]
