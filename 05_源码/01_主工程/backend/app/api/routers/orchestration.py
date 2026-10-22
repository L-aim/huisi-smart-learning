from __future__ import annotations

import importlib
import json
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.agents.trace_log import count_entries, read_entries
from app.core.config import settings
from app.core.ids import new_id
from app.schemas import ApiResponse


router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])

MULTI_AGENT_REGISTRY = os.getenv("MULTI_AGENT_REGISTRY", "mcp_server.services")
MULTI_AGENT_TRACE_FILENAME = "multi_agent_trace.json"


class MultiAgentRequest(BaseModel):
    student_id: str = Field(min_length=1)
    role_name: str = ""
    role_id: str = ""
    answer: str = "B"
    timeout_seconds: int = Field(default=180, ge=10, le=600)

TRACE_FILENAME = "role_pipeline_trace.json"
LIVE_LIMIT = 12
TRACE_HINT = (
    "尚无整链运行期记录。在 backend 目录执行 "
    "python ../scripts/run_role_pipeline_trace.py demo 前端开发工程师 "
    "跑一次真实的九步编排，本接口就会返回那一次每一步的工具、角色与传值；"
    "页面的 live 段则来自真实接口调用，不需要跑脚本。"
)


@router.get("/trace", response_model=ApiResponse)
async def trace() -> ApiResponse:
    """返回整链运行期记录 + 真实操作留痕。

    只读：本接口不会触发任何工具调用。``steps`` 来自
    ``scripts/run_role_pipeline_trace.py`` 落盘的那一次九步编排，
    ``live`` 来自 ``app/agents/trace_log.py`` 记录的真实 HTTP 调用。
    两者都没有时明确返回 ``available=false`` 与生成方法，绝不返回占位数据冒充「跑过了」。
    """
    request_id = new_id()
    live = read_entries(LIVE_LIMIT)
    live_total = count_entries()
    path = settings.data_path / TRACE_FILENAME
    if not path.exists():
        return ApiResponse(
            request_id=request_id,
            success=True,
            data={
                "available": False,
                "trace_file": str(path),
                "hint": TRACE_HINT,
                "steps": [],
                "live": live,
                "live_total": live_total,
            },
        )

    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # 文件损坏也要如实报，不能吞掉
        return ApiResponse(
            request_id=request_id,
            success=False,
            error={"code": "TRACE_UNREADABLE", "message": str(e)},
        )

    if not isinstance(payload, dict):
        return ApiResponse(
            request_id=request_id,
            success=False,
            error={"code": "TRACE_INVALID", "message": "trace 文件顶层不是对象"},
        )

    steps = payload.get("steps")
    return ApiResponse(
        request_id=request_id,
        success=True,
        data={
            "available": True,
            "trace_file": str(path),
            "source": payload.get("source"),
            "generated_at": payload.get("generated_at"),
            "student_id": payload.get("student_id"),
            "role_name": payload.get("role_name"),
            "runtime_ok": payload.get("ok"),
            "runtime_error": payload.get("error"),
            "steps": steps if isinstance(steps, list) else [],
            "live": live,
            "live_total": live_total,
        },
    )


@router.post("/multi-agent", response_model=ApiResponse)
async def multi_agent(req: MultiAgentRequest) -> ApiResponse:
    """真实多进程角色编排：一个角色一个操作系统进程，主控只做调度与传值。

    与 ``/trace`` 的区别：``/trace`` 读的是历史落盘记录（只读），本接口**当场起进程串一遍**，
    所以返回里的 ``workers`` 是真实的 ``pid``，可以用它证明「角色 = 进程」而不是「一个循环里换了个名字」。

    失败口径（绝不降级成假成功）：
    - 注册表模块 import 不了 → ``MULTI_AGENT_REGISTRY_UNAVAILABLE``
    - 步骤所需工具不在注册表 → ``MULTI_AGENT_BINDING_MISSING``
    - 工具返回 ok=false → 原样回传 ``stop_reason``，``ok=false``
    """
    request_id = new_id()
    try:
        module = importlib.import_module(MULTI_AGENT_REGISTRY)
    except Exception as e:  # noqa: BLE001
        return ApiResponse(
            request_id=request_id,
            success=False,
            error={
                "code": "MULTI_AGENT_REGISTRY_UNAVAILABLE",
                "message": f"无法导入注册表模块 {MULTI_AGENT_REGISTRY}：{type(e).__name__}: {e}",
            },
        )
    del module

    from app.agents.multi_agent import MultiAgentRuntime

    missing = await run_in_threadpool(MultiAgentRuntime.missing_bindings, MULTI_AGENT_REGISTRY)
    if missing:
        return ApiResponse(
            request_id=request_id,
            success=True,
            data={
                "available": False,
                "runtime": "multiprocess",
                "registry": MULTI_AGENT_REGISTRY,
                "missing_tools": missing,
                "steps": [],
                "workers": {},
                "hint": "注册表里缺少步骤所需工具，编排不会执行（不返回占位步骤冒充跑过）。",
            },
        )

    runtime = MultiAgentRuntime(MULTI_AGENT_REGISTRY, timeout=float(req.timeout_seconds))
    result = await run_in_threadpool(
        runtime.run,
        req.student_id,
        answer=req.answer,
        role_name=req.role_name,
        role_id=req.role_id,
    )

    data = {
        "available": True,
        "runtime": "multiprocess",
        "registry": MULTI_AGENT_REGISTRY,
        "student_id": req.student_id,
        "role_name": req.role_name,
        "ok": result.get("ok"),
        "workers": result.get("workers") or {},
        "steps": result.get("steps") or [],
        "stop_reason": result.get("stop_reason") or {},
        "context": {
            key: (str(value)[:200] if not isinstance(value, (int, float, bool)) else value)
            for key, value in (result.get("context") or {}).items()
        },
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        path = settings.data_path / MULTI_AGENT_TRACE_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        # 落盘只是留痕，失败不能影响本次真实结果
        pass
    if result.get("ok"):
        return ApiResponse(request_id=request_id, success=True, data=data)
    # 业务失败也要带原因出信封：否则前端只能显示「失败但没有原因」，等于把可解释性丢了
    stop = data["stop_reason"] or {}
    return ApiResponse(
        request_id=request_id,
        success=False,
        data=data,
        error={
            "code": stop.get("code") or "MULTI_AGENT_STEP_FAILED",
            "message": stop.get("message") or f"第 {len(data['steps'])} 步失败，未返回原因",
        },
    )
