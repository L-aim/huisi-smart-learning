"""
服务外包创新创业大赛A13赛道
A组员-岗位图谱组 核心：JD信息自动提取模块
完成标准：非结构化JD文本转结构化岗位画像
"""
import json
import re
from job_schema import JobProfile, SkillRequire

class JobExtractor:
    def __init__(self):
        # 硬技能关键词库（可根据行业扩展）
        self.hard_skill_keywords = [
            "Java", "Python", "SQL", "Spring Boot", "Spring Cloud", "MySQL", "Redis", "MQ",
            "HTML", "CSS", "JavaScript", "Vue", "React", "Node.js", "Figma", "PS", "AI",
            "Axure", "XMind", "PRD", "Tableau", "Power BI", "Postman", "Jmeter", "自动化测试",
            "文案写作", "内容策划", "视频剪辑", "品牌策略", "商务谈判", "招聘", "劳动法"
        ]
        # 软技能关键词库
        self.soft_skill_keywords = [
            "沟通能力", "团队协作", "逻辑思维", "用户思维", "项目管理", "跨团队沟通",
            "问题解决能力", "学习能力", "执行力", "抗压能力", "目标感", "审美能力",
            "市场洞察", "创意能力", "细心严谨", "亲和力", "保密意识"
        ]
        # 学历正则
        self.education_pattern = re.compile(r"(大专|本科|硕士|博士)(?:及以上)?")
        # 经验正则
        self.experience_pattern = re.compile(r"(\d+年(?:以上|以内)?|应届生可投)")

    def clean_text(self, text: str) -> str:
        """文本清洗，去除多余空格和换行"""
        return text.replace("\n", " ").replace("\r", " ").strip()

    def extract_skills(self, jd_text: str) -> SkillRequire:
        """从JD文本中提取硬技能和软技能"""
        hard_skills = []
        soft_skills = []
        # 匹配硬技能
        for skill in self.hard_skill_keywords:
            if skill in jd_text:
                hard_skills.append(skill)
        # 匹配软技能
        for skill in self.soft_skill_keywords:
            if skill in jd_text:
                soft_skills.append(skill)
        # 去重+默认兜底
        hard_skills = list(set(hard_skills)) if hard_skills else []
        soft_skills = list(set(soft_skills)) if soft_skills else ["沟通能力", "团队协作", "学习能力"]
        return SkillRequire(hard_skills=hard_skills, soft_skills=soft_skills)

    def extract_education(self, jd_text: str) -> list:
        """提取学历要求"""
        match = self.education_pattern.findall(jd_text)
        if match:
            return [f"{item}及以上" for item in match]
        return ["本科及以上"]

    def extract_experience(self, jd_text: str) -> str:
        """提取工作经验要求"""
        match = self.experience_pattern.findall(jd_text)
        if match:
            return match[0]
        return "3年以内"

    def extract_responsibility(self, jd_text: str) -> list:
        """提取岗位职责"""
        # 简单分句提取，可根据JD格式优化
        sentences = re.split(r"[；;。.123456789、]", jd_text)
        responsibilities = []
        for sent in sentences:
            sent = sent.strip()
            if len(sent) > 10 and ("负责" in sent or "参与" in sent or "完成" in sent):
                responsibilities.append(sent)
        return responsibilities[:5]  # 取前5条核心职责

    def extract_job_profile(self, jd_raw: dict) -> JobProfile:
        """
        核心功能：从原始JD中提取结构化岗位画像
        :param jd_raw: 原始JD数据，包含job_id、job_name、job_category、jd_text
        :return: 标准化岗位画像对象
        """
        # 基础信息提取
        job_id = jd_raw.get("job_id", "")
        job_name = jd_raw.get("job_name", "")
        job_category = jd_raw.get("job_category", "")
        jd_text = self.clean_text(jd_raw.get("jd_text", ""))

        # 全维度信息提取
        skill_require = self.extract_skills(jd_text)
        education_require = self.extract_education(jd_text)
        experience_require = self.extract_experience(jd_text)
        job_responsibility = self.extract_responsibility(jd_text)

        # 构建完整岗位画像
        job_profile = JobProfile(
            job_id=job_id,
            job_name=job_name,
            job_category=job_category,
            skill_require=skill_require,
            education_require=education_require,
            experience_require=experience_require,
            job_responsibility=job_responsibility,
            core_competency=skill_require.hard_skills[:3]
        )
        return job_profile

# 批量解析工具
def batch_parse_jobs(jd_list: list) -> list:
    extractor = JobExtractor()
    result = []
    for jd in jd_list:
        profile = extractor.extract_job_profile(jd)
        result.append(profile.dict())
    return result

if __name__ == "__main__":
    # 测试批量解析
    with open("岗位JD原始数据.json", "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    parsed_data = batch_parse_jobs(raw_data["job_list"])
    with open("structured_job_data.json", "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, ensure_ascii=False, indent=2)
    print(f"批量解析完成，共解析{len(parsed_data)}个岗位")