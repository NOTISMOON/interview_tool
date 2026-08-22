"""简历解析 LLM 输出模型（LangGraph 结构化提取结果）。

由 LLM 结构化输出层解析后经 Pydantic 校验，再映射到 resume 表
parsed_* JSON 字段与 resume_work_experience 表行。
"""

from pydantic import BaseModel, Field


class EducationItem(BaseModel):
    """教育经历单项。"""

    school: str = Field(default="", description="学校名称")
    degree: str | None = Field(None, description="学历（本科/硕士/博士等）")
    major: str | None = Field(None, description="专业")
    duration: str | None = Field(None, description="就读时间，如 2016-2020")


class ProjectItem(BaseModel):
    """项目经历单项。"""

    name: str = Field(default="", description="项目名称")
    description: str | None = Field(None, description="项目描述（负责内容/成果）")
    tech_stack: list[str] = Field(default_factory=list, description="使用的技术栈")


class WorkItem(BaseModel):
    """工作经历单项（落 resume_work_experience 表）。

    company/role 放宽为可空：DeepSeek json_mode 输出不稳定，缺失或显式 null
    都可能出现，若强制非空会使整个结构化解析偶发失败（简历被误判 status=2）。
    """

    company: str | None = Field(None, description="公司名称")
    role: str | None = Field(None, description="职位")
    duration: str | None = Field(None, description="任职时间")
    description: str | None = Field(None, description="工作描述")


class ResumeExtraction(BaseModel):
    """简历结构化提取结果。"""

    name: str | None = Field(None, description="候选人姓名")
    skills: list[str] = Field(default_factory=list, description="技能列表")
    education: list[EducationItem] = Field(default_factory=list, description="教育经历")
    projects: list[ProjectItem] = Field(default_factory=list, description="项目经历")
    work_experience: list[WorkItem] = Field(default_factory=list, description="工作经历")
