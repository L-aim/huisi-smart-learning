"""
服务外包创新创业大赛A13赛道
A组员-岗位图谱组 核心：对外API接口
完成标准：给B组（人岗匹配）、C组（前端/报告）提供标准化HTTP接口
优化内容：1. 增加分页功能 2. 完善入参校验 3. 增强异常处理
"""
from fastapi import FastAPI, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel, Field
from job_database import JobDatabase
from job_vector import JobVectorBuilder
from job_graph import JobGraphBuilder

# 初始化FastAPI应用
app = FastAPI(
    title="服务外包大赛A13-岗位图谱API服务",
    description="A组员-岗位图谱组对外接口，为B/C组提供数据支撑",
    version="1.0.0"
)

# 初始化核心模块
db = JobDatabase()
vector_builder = JobVectorBuilder()
graph_builder = JobGraphBuilder()

# 请求体模型（增加入参校验）
class SimilarJobRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="用户能力描述/简历文本，长度1-2000")
    top_k: int = Field(default=5, ge=1, le=20, description="返回相似岗位数量，范围1-20")

# ==================== 核心API接口 ====================
# 健康检查接口
@app.get("/", summary="服务健康检查", tags=["基础接口"])
def health_check():
    try:
        job_count = len(db.get_all_jobs())
        return {
            "code": 200,
            "msg": "岗位图谱API服务运行正常",
            "data": {
                "total_jobs": job_count
            }
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"服务初始化异常：{str(e)}")

# 获取所有岗位列表（增加分页功能）
@app.get("/job/list", summary="获取全量岗位列表", tags=["岗位数据接口"])
def get_job_list(
    category: Optional[str] = None,
    page: int = Query(default=1, ge=1, description="页码，从1开始"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量，范围1-100")
):
    try:
        if category:
            job_list = db.get_jobs_by_category(category)
        else:
            job_list = db.get_all_jobs()
        
        # 分页处理
        total = len(job_list)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_jobs = job_list[start:end]
        
        return {
            "code": 200,
            "msg": "获取成功",
            "count": len(paginated_jobs),
            "total": total,
            "page": page,
            "page_size": page_size,
            "data": [job.dict() for job in paginated_jobs]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取岗位列表失败：{str(e)}")

# 获取岗位详情
@app.get("/job/detail/{job_id}", summary="获取岗位详情", tags=["岗位数据接口"])
def get_job_detail(job_id: str):
    try:
        job = db.get_job_by_id(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"岗位ID {job_id} 不存在")
        return {
            "code": 200,
            "msg": "获取成功",
            "data": job.dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取岗位详情失败：{str(e)}")

# 相似岗位检索（B组人岗匹配核心接口，已优化可解释性）
@app.post("/job/similar", summary="相似岗位检索", tags=["向量检索接口"])
def search_similar_jobs(request: SimilarJobRequest):
    try:
        result = vector_builder.search_similar_jobs(request.text, request.top_k)
        return {
            "code": 200,
            "msg": "检索成功",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检索失败：{str(e)}")

# 获取岗位晋升/换岗路径（增加path_type枚举校验）
@app.get("/job/path/{job_id}", summary="获取岗位职业路径", tags=["岗位图谱接口"])
def get_job_path(
    job_id: str,
    path_type: Optional[str] = Query(None, regex="^(vertical|horizontal)$", description="路径类型：vertical=晋升/horizontal=换岗")
):
    try:
        job = db.get_job_by_id(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"岗位ID {job_id} 不存在")
        
        paths = graph_builder.get_job_paths(job_id, path_type)
        return {
            "code": 200,
            "msg": "获取成功",
            "data": {
                "job_id": job_id,
                "job_name": job.job_name,
                "path_list": [p.dict() for p in paths]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取职业路径失败：{str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)