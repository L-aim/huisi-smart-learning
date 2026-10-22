"""
服务外包创新创业大赛A13赛道
A组员-岗位图谱组 核心：岗位数据库管理模块
完成标准：岗位数据增删改查、批量读取、分类筛选
"""
import json
from typing import List, Optional
from job_schema import JobProfile

class JobDatabase:
    def __init__(self, data_path: str = None):
        # 如果没有指定路径，尝试多个可能的路径
        if data_path is None:
            import os
            possible_paths = [
                "结构化岗位画像.json",
                "../数据文件/结构化岗位画像.json",
                os.path.join(os.path.dirname(__file__), "../数据文件/结构化岗位画像.json"),
                os.path.join(os.path.dirname(os.path.dirname(__file__)), "数据文件/结构化岗位画像.json"),
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    data_path = path
                    break
            if data_path is None:
                data_path = "结构化岗位画像.json"  # 默认值

        self.data_path = data_path
        self.job_list: List[JobProfile] = []
        self._init_database()

    def _init_database(self):
        """初始化数据库，加载本地数据"""
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.job_list = [JobProfile(**item) for item in data]
        except Exception as e:
            print(f"数据库加载失败：{str(e)}")
            self.job_list = []

    def _save_data(self):
        """保存数据到本地文件"""
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump([job.dict() for job in self.job_list], f, ensure_ascii=False, indent=2)

    # 获取所有岗位
    def get_all_jobs(self) -> List[JobProfile]:
        return self.job_list

    # 根据ID获取岗位详情
    def get_job_by_id(self, job_id: str) -> Optional[JobProfile]:
        for job in self.job_list:
            if job.job_id == job_id:
                return job
        return None

    # 根据分类获取岗位
    def get_jobs_by_category(self, category: str) -> List[JobProfile]:
        return [job for job in self.job_list if job.job_category == category]

    # 新增岗位
    def add_job(self, job_profile: JobProfile) -> bool:
        if self.get_job_by_id(job_profile.job_id):
            return False
        self.job_list.append(job_profile)
        self._save_data()
        return True

    # 更新岗位
    def update_job(self, job_id: str, update_data: dict) -> bool:
        job = self.get_job_by_id(job_id)
        if not job:
            return False
        for key, value in update_data.items():
            if hasattr(job, key):
                setattr(job, key, value)
        self._save_data()
        return True

    # 删除岗位
    def delete_job(self, job_id: str) -> bool:
        job = self.get_job_by_id(job_id)
        if not job:
            return False
        self.job_list.remove(job)
        self._save_data()
        return True

if __name__ == "__main__":
    db = JobDatabase()
    print(f"岗位数据库加载完成，共{len(db.get_all_jobs())}个岗位")