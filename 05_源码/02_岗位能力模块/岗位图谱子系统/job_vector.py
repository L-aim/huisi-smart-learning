"""
服务外包创新创业大赛A13赛道
A组员-岗位图谱组 核心：岗位向量库构建模块
完成标准：生成每个岗位的向量表示，支持人岗匹配、相似岗位检索
优化内容：1. 替换为中文多语言模型 2. 增加匹配详情可解释性
"""
import json
import numpy as np
import faiss
from typing import List, Tuple
from sentence_transformers import SentenceTransformer
from job_database import JobDatabase
from job_schema import JobProfile

class JobVectorBuilder:
    def __init__(self, vector_dim: int = 384, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        # 已优化为中文多语言模型，大幅提升中文语义匹配精度
        self.vector_dim = vector_dim
        self.model_name = model_name
        self.model = None  # 延迟加载模型
        self.db = JobDatabase()
        self.id_map: List[str] = []
        self.index = None
        self.vector_data = None
        self.job_text_map = {}  # 存储岗位文本用于匹配度解释
        self._model_loaded = False

    def _load_model(self):
        """延迟加载模型，只在需要时加载"""
        if not self._model_loaded:
            try:
                print("正在加载向量检索模型...")
                self.model = SentenceTransformer(self.model_name)
                self._model_loaded = True
                print("向量检索模型加载成功！")
            except Exception as e:
                print(f"警告：模型加载失败 ({e})，向量检索功能将不可用")
                self.model = None
                self._model_loaded = True

    def _job_to_text(self, job: JobProfile) -> str:
        """岗位画像全维度转文本，最大化语义信息，提升检索精度"""
        text = f"""
        岗位名称：{job.job_name}
        岗位分类：{job.job_category}
        硬技能要求：{"、".join(job.skill_require.hard_skills)}
        软技能要求：{"、".join(job.skill_require.soft_skills)}
        工作经验要求：{job.experience_require}
        学历要求：{"、".join(job.education_require)}
        核心岗位职责：{"；".join(job.job_responsibility)}
        岗位核心能力：{"、".join(job.core_competency)}
        """
        return text.strip()

    def build_vector_db(self):
        """全量构建岗位向量库，生成faiss索引，支持高效检索"""
        # 延迟加载模型
        self._load_model()

        if self.model is None:
            raise Exception("模型加载失败，无法构建向量库")

        job_list = self.db.get_all_jobs()
        if not job_list:
            raise Exception("岗位数据库为空，无法构建向量库")

        # 生成岗位ID映射和文本映射
        self.id_map = [job.job_id for job in job_list]
        self.job_text_map = {job.job_id: self._job_to_text(job) for job in job_list}

        # 生成岗位文本列表
        job_text_list = [self._job_to_text(job) for job in job_list]
        # 生成真实语义向量
        self.vector_data = self.model.encode(job_text_list, normalize_embeddings=True)
        
        # 构建faiss索引，提升检索速度
        self.index = faiss.IndexFlatIP(self.vector_dim)
        self.index.add(self.vector_data.astype(np.float32))
        
        # 保存向量库和映射文件
        np.save("job_vectors.npy", self.vector_data)
        faiss.write_index(self.index, "job_vector_index.faiss")
        with open("job_vector_id_map.json", "w", encoding="utf-8") as f:
            json.dump(self.id_map, f, ensure_ascii=False, indent=2)
        
        print(f"岗位向量库构建完成，共{len(self.id_map)}个岗位向量，维度：{self.vector_dim}")

    def load_vector_db(self):
        """加载本地已构建的向量库，避免重复生成"""
        try:
            self.vector_data = np.load("job_vectors.npy")
            self.index = faiss.read_index("job_vector_index.faiss")
            with open("job_vector_id_map.json", "r", encoding="utf-8") as f:
                self.id_map = json.load(f)
            # 重新构建文本映射
            job_list = self.db.get_all_jobs()
            self.job_text_map = {job.job_id: self._job_to_text(job) for job in job_list}
            print(f"向量库加载成功，共{len(self.id_map)}个岗位向量")
        except Exception as e:
            print(f"向量库加载失败，将重新构建：{str(e)}")
            self.build_vector_db()

    def search_similar_jobs(self, query_text: str, top_k: int = 5) -> List[dict]:
        """
        相似岗位检索（B组人岗匹配核心接口）
        输入：用户简历文本/能力描述，返回top_k个相似岗位，包含岗位ID、相似度和匹配详情
        优化：增加匹配度可解释性，返回岗位详情
        """
        # 延迟加载模型
        self._load_model()

        if self.model is None:
            # 如果模型加载失败，返回基于关键词匹配的简化结果
            return self._keyword_search(query_text, top_k)

        if self.index is None:
            self.load_vector_db()

        # 生成查询文本的向量
        query_vector = self.model.encode([query_text], normalize_embeddings=True).astype(np.float32)
        # 检索top_k相似向量
        distances, indices = self.index.search(query_vector, min(top_k, len(self.id_map)))
        
        # 格式化返回结果，增加可解释性
        result = []
        for dist, idx in zip(distances[0], indices[0]):
            job_id = self.id_map[idx]
            job = self.db.get_job_by_id(job_id)
            result.append({
                "job_id": job_id,
                "job_name": job.job_name if job else "",
                "similarity_score": round(float(dist), 4),
                "match_reason": self._generate_match_reason(query_text, job) if job else ""
            })
        return result

    def _keyword_search(self, query_text: str, top_k: int = 5) -> List[dict]:
        """
        关键词搜索的后备方案（当向量模型加载失败时使用）
        基于关键词匹配返回相似岗位
        """
        job_list = self.db.get_all_jobs()
        results = []

        for job in job_list:
            score = 0
            # 检查技能匹配
            for skill in job.skill_require.hard_skills:
                if skill.lower() in query_text.lower():
                    score += 10

            # 检查岗位名称匹配
            if job.job_name in query_text:
                score += 20

            # 检查软技能匹配
            for soft_skill in job.skill_require.soft_skills:
                if soft_skill in query_text:
                    score += 5

            if score > 0:
                results.append({
                    "job_id": job.job_id,
                    "job_name": job.job_name,
                    "similarity_score": min(score / 100, 1.0),  # 归一化到0-1
                    "match_reason": "基于关键词匹配（向量检索暂不可用）"
                })

        # 按分数排序并返回top_k
        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return results[:top_k]

    def _generate_match_reason(self, query_text: str, job: JobProfile) -> str:
        """简单的匹配度解释生成逻辑，提升可解释性"""
        reasons = []
        # 检查硬技能匹配
        for skill in job.skill_require.hard_skills:
            if skill in query_text:
                reasons.append(f"具备{skill}技能")
        # 检查经验匹配
        if job.experience_require in query_text:
            reasons.append(f"符合{job.experience_require}经验要求")
        # 检查岗位名称匹配
        if job.job_name in query_text:
            reasons.append(f"有{job.job_name}相关经验")
        
        if reasons:
            return "匹配原因：" + "、".join(reasons[:3])
        else:
            return "综合能力匹配"

if __name__ == "__main__":
    builder = JobVectorBuilder()
    builder.build_vector_db()
    # 测试检索
    test_result = builder.search_similar_jobs("会Java开发，熟悉Spring Boot，有3年后端开发经验", top_k=3)
    print("测试检索结果：", test_result)