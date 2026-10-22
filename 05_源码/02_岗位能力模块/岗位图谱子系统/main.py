"""
服务外包创新创业大赛A13赛道
A组员-岗位图谱组 项目主入口
"""
from fastapi import FastAPI
from job_api import app as job_api_app

# 初始化主应用
app = FastAPI(
    title="服务外包大赛A13-大学生职业发展规划系统",
    description="A13赛道参赛项目-岗位画像子系统",
    version="1.0.0"
)

# 挂载岗位图谱API
app.mount("/api", job_api_app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)