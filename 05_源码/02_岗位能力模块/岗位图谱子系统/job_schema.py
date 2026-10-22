"""
服务外包创新创业大赛A13赛道
A组员-岗位图谱组 核心：岗位画像标准Schema
完成标准：8+核心维度定义，全项目数据规范基础
"""
from pydantic import BaseModel, Field
from typing import List, Optional

# 技能子模型
class SkillRequire(BaseModel):
    hard_skills: List[str] = Field(default_factory=list, description="岗位硬技能要求，如Python、Java、SQL等")
    soft_skills: List[str] = Field(default_factory=list, description="岗位软技能要求，如沟通协作、项目管理等")

# 岗位画像核心Schema（8+核心维度，完全符合大赛要求）
class JobProfile(BaseModel):
    # 维度1：岗位基础信息
    job_id: str = Field(description="岗位唯一ID")
    job_name: str = Field(description="岗位名称")
    job_category: str = Field(description="岗位分类：技术/产品/设计/运营/市场/职能")
    city: Optional[List[str]] = Field(default_factory=list, description="工作城市")
    # 维度2：技能要求
    skill_require: SkillRequire = Field(description="岗位硬技能+软技能要求")
    # 维度3：学历与证书要求
    education_require: List[str] = Field(default_factory=list, description="学历要求")
    certificate_require: List[str] = Field(default_factory=list, description="证书要求")
    # 维度4：工作经验要求
    experience_require: str = Field(description="工作经验要求")
    # 维度5：核心岗位职责
    job_responsibility: List[str] = Field(default_factory=list, description="核心工作内容与职责")
    # 维度6：岗位核心能力
    core_competency: List[str] = Field(default_factory=list, description="岗位核心能力要求")
    # 维度7：薪资与行业信息
    salary_range: Optional[str] = Field(default=None, description="薪资区间")
    industry: Optional[List[str]] = Field(default_factory=list, description="所属行业")
    # 维度8：岗位关联图谱信息
    related_jobs: List[str] = Field(default_factory=list, description="关联岗位ID，用于晋升/换岗图谱")

# 岗位路径模型（晋升/换岗用）
class JobPath(BaseModel):
    from_job_id: str = Field(description="起始岗位ID")
    to_job_id: str = Field(description="目标岗位ID")
    path_type: str = Field(description="路径类型：vertical垂直晋升/horizontal横向换岗")
    path_desc: str = Field(description="路径说明")
    required_skills: List[str] = Field(default_factory=list, description="转岗/晋升所需技能")