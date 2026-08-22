"""简历相关请求/响应模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


class ResumeWorkExperienceOut(BaseModel):
    """简历工作经历输出模型。"""

    id: int = Field(..., description="工作经历ID")
    company: str = Field(..., description="公司名称")
    role: str = Field(..., description="职位")
    duration: str | None = Field(None, description="任职时间")
    description: str | None = Field(None, description="工作描述")
    sort_order: int = Field(0, description="排序")

    model_config = {"from_attributes": True}


class ResumeOut(BaseModel):
    """简历输出模型（列表项/详情）。"""

    id: int = Field(..., description="简历ID")
    user_id: int = Field(..., description="所属用户ID")
    file_name: str = Field(..., description="原始文件名")
    file_url: str | None = Field(None, description="文件访问URL")
    file_size: int | None = Field(None, description="文件大小（字节）")
    status: int = Field(..., description="解析状态 0-解析中 1-就绪 2-错误")
    parsed_name: str | None = Field(None, description="解析出的姓名")
    parsed_skills: list[str] | None = Field(None, description="解析出的技能列表")
    parsed_education: list[dict] | None = Field(None, description="解析出的教育经历数组")
    parsed_projects: list[dict] | None = Field(None, description="解析出的项目经历数组")
    error_message: str | None = Field(None, description="解析失败原因")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    work_experiences: list[ResumeWorkExperienceOut] = Field(
        default_factory=list, description="工作经历列表"
    )

    model_config = {"from_attributes": True}


class ResumeListResponse(BaseModel):
    """简历列表响应模型（分页）。"""

    items: list[ResumeOut] = Field(..., description="简历列表")
    total: int = Field(..., description="简历总数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="页大小")
