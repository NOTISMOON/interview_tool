"""文件上传请求/响应模型。"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# 允许的文件用途
ALLOWED_FILE_TYPES = ("resume", "avatar", "post_image")


class StsTokenRequest(BaseModel):
    """STS 临时密钥申请请求模型。"""

    file_name: str = Field(..., min_length=1, max_length=255, description="原始文件名（用于提取扩展名）")
    file_type: str = Field(..., description="文件用途：resume（简历）/ image（图片）")
    file_size: int = Field(..., gt=0, description="文件大小（字节）")
    content_type: str = Field(..., max_length=100, description="文件MIME类型")

    @field_validator("file_type")
    @classmethod
    def validate_file_type(cls, v: str) -> str:
        """校验文件用途必须在允许列表内。"""
        if v not in ALLOWED_FILE_TYPES:
            raise ValueError(f"file_type 仅支持 resume / avatar / post_image，当前值: {v}")
        return v


class StsCredentials(BaseModel):
    """STS 临时密钥凭证。"""

    tmp_secret_id: str = Field(..., description="临时SecretId")
    tmp_secret_key: str = Field(..., description="临时SecretKey")
    session_token: str = Field(..., description="会话Token")
    expired_time: int = Field(..., description="密钥过期时间（Unix时间戳）")


class StsTokenResponse(BaseModel):
    """STS 临时密钥响应模型（前端凭此直传COS）。"""

    credentials: StsCredentials
    cos_key: str = Field(..., description="后端生成的COS对象Key（上传目标路径）")
    bucket: str = Field(..., description="COS Bucket名称")
    region: str = Field(..., description="COS地域")
    upload_url: str = Field(..., description="COS上传基础URL")
    expire_time: int = Field(..., description="密钥剩余有效期（秒）")


class UploadCallbackRequest(BaseModel):
    """上传完成回调请求模型（前端直传成功后通知后端）。"""

    cos_key: str = Field(..., min_length=1, max_length=500, description="COS对象Key")
    file_name: str = Field(..., min_length=1, max_length=255, description="原始文件名")
    file_size: int = Field(..., gt=0, description="文件大小（字节）")
    content_type: str = Field(..., max_length=100, description="文件MIME类型")
    etag: str = Field(..., min_length=1, max_length=100, description="文件ETag（COS返回）")
    location: str = Field(..., max_length=1000, description="对象访问地址（COS返回）")


class UploadCallbackResponse(BaseModel):
    """上传回调响应模型。"""

    upload_id: int = Field(..., description="上传记录ID")
    cos_key: str = Field(..., description="COS对象Key")
    file_url: str = Field(..., description="文件访问URL")
    status: str = Field(..., description="上传状态：completed")
    created_at: datetime = Field(..., description="记录创建时间")
    resume_id: int | None = Field(
        None, description="简历ID（仅file_type=resume时返回，供前端轮询分析状态）"
    )
    resume_status: int | None = Field(
        None, description="简历解析状态（0-解析中 1-就绪 2-错误，仅简历上传返回）"
    )

    model_config = {"from_attributes": True, "populate_by_name": True}


class UploadRecordResponse(BaseModel):
    """上传记录响应模型（列表项）。"""

    upload_id: int = Field(..., description="上传记录ID")
    file_type: str = Field(..., description="文件用途：resume/avatar")
    file_name: str = Field(..., description="原始文件名")
    file_size: int = Field(..., description="文件大小（字节）")
    content_type: str = Field(..., description="MIME类型")
    file_url: str = Field(..., description="文件访问URL")
    status: str = Field(..., description="状态：pending/completed/failed")
    created_at: datetime = Field(..., description="上传时间")

    model_config = {"from_attributes": True, "populate_by_name": True}


class UploadRecordListResponse(BaseModel):
    """上传记录列表响应模型（分页）。"""

    items: list[UploadRecordResponse]
    total: int = Field(..., description="符合条件的记录总数")
    page: int = Field(..., description="当前页码（从1开始）")
    page_size: int = Field(..., description="页大小")
