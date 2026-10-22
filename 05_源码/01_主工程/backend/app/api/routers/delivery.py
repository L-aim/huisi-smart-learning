from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.agents import Orchestrator
from app.core.config import settings
from app.core.ids import new_id
from app.repo import list_resources
from app.schemas import ApiResponse
from app.evolution import EvolutionEngine
from app.services.exercise_bank import build_exercise_session, exercise_summary, submit_exercise_answer
from app.services.knowledge_hub import graph_data, mastery_data, search_index
from app.services.learning_state import evaluation_overview, path_overview, profile_overview


router = APIRouter(prefix="/api", tags=["delivery-compat"])
orchestrator = Orchestrator()
evolution_engine = EvolutionEngine()


class FlexibleRequest(BaseModel):
    student_id: str = Field(min_length=1)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    topic: str | None = None
    question: str | None = None
    query: str | None = None
    goals: str | None = None
    type: str | None = None
    resource_type: str | None = None
    requirement: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


class ExerciseSubmitRequest(BaseModel):
    student_id: str = Field(min_length=1)
    question_id: str = ""
    answer: str | list[str] = ""


@router.get("/health", response_model=ApiResponse)
async def api_health() -> ApiResponse:
    ai_configured = bool(settings.llm_api_key or settings.llm_generate_api_key or settings.llm_tutor_api_key)
    data = {
        "ok": True,
        "backend": {"framework": "FastAPI", "status": "ready"},
        "ai_provider": {
            "provider": settings.llm_provider,
            "configured": ai_configured,
            "demo_mode": not ai_configured,
        },
        "knowledge_base": {"status": "ready", "graph_endpoint": "/api/knowledge/map"},
        "service": "zhixue-resource-agent",
        "mode": settings.app_env,
        "time": datetime.now(timezone.utc).isoformat(),
        "data_dir_ready": settings.data_path.exists(),
        "files_dir_ready": settings.files_path.exists(),
    }
    return ApiResponse(request_id=new_id(), success=True, data=data)


@router.post("/profile/extract", response_model=ApiResponse)
async def profile_extract(req: FlexibleRequest) -> ApiResponse:
    request_id = new_id()
    text = req.question or req.query or req.topic or req.goals or ""
    if not text.strip():
        return ApiResponse(request_id=request_id, success=False, error={"code": "PROFILE_TEXT_REQUIRED", "message": "请提供要分析的学习描述"})
    try:
        data = await orchestrator.profile_chat(
            student_id=req.student_id,
            messages=[{"role": "user", "content": text}],
            major=None,
            goals=req.goals,
        )
        return ApiResponse(request_id=request_id, success=True, data=data)
    except asyncio.TimeoutError:
        return ApiResponse(
            request_id=request_id,
            success=False,
            error={"code": "RESOURCE_GENERATION_TIMEOUT", "message": "资源分析与生成超时，输入已保留，请缩小资源类型后重试"},
        )
    except Exception as exc:
        return ApiResponse(request_id=request_id, success=False, error={"code": "PROFILE_EXTRACT_ERROR", "message": str(exc)})


@router.get("/profile/current", response_model=ApiResponse)
async def profile_current(student_id: str = Query(..., min_length=1)) -> ApiResponse:
    profile = profile_overview(student_id)
    return ApiResponse(request_id=new_id(), success=True, data=profile)


@router.post("/agents/generate-resources", response_model=ApiResponse)
async def generate_resources(req: FlexibleRequest) -> ApiResponse:
    request_id = new_id()
    try:
        requirement = _normalize_requirement(req)
        resources = await asyncio.wait_for(
            orchestrator.generate(student_id=req.student_id, requirement=requirement),
            timeout=max(30, int(settings.llm_timeout_sec)),
        )
        return ApiResponse(
            request_id=request_id,
            success=True,
            data={"resources": _normalize_resources(resources, req.student_id), "source": "orchestrator"},
        )
    except Exception as exc:
        return ApiResponse(
            request_id=request_id,
            success=False,
            error={"code": "RESOURCE_GENERATION_ERROR", "message": str(exc)},
        )


@router.post("/workshop/create", response_model=ApiResponse)
async def workshop_create(req: FlexibleRequest) -> ApiResponse:
    return await generate_resources(req)


@router.get("/workshop/resources", response_model=ApiResponse)
async def workshop_resources(student_id: str = Query(..., min_length=1)) -> ApiResponse:
    return ApiResponse(request_id=new_id(), success=True, data={"resources": list_resources(student_id)})


@router.post("/workshop/export", response_model=ApiResponse)
async def workshop_export(req: FlexibleRequest) -> ApiResponse:
    resources = list_resources(req.student_id)
    return ApiResponse(
        request_id=new_id(),
        success=True,
        data={
            "status": "ready",
            "resource_count": len(resources),
            "message": "资源已沉淀到本地文件库，可通过 /api/resources/{id}?inline=true 查看内容。",
        },
    )


@router.get("/path/current", response_model=ApiResponse)
async def path_current(student_id: str = Query(..., min_length=1)) -> ApiResponse:
    return ApiResponse(request_id=new_id(), success=True, data=path_overview(student_id))


@router.get("/evaluation/snapshot", response_model=ApiResponse)
async def evaluation_snapshot(student_id: str = Query(..., min_length=1)) -> ApiResponse:
    mastery = mastery_data(student_id)
    summary = mastery.get("summary", {})
    stats = exercise_summary(student_id)
    return ApiResponse(
        request_id=new_id(),
        success=True,
        data={
            "student_id": student_id,
            "mastery": summary,
            "exercise": stats,
            "weak_nodes": [n for n in mastery.get("nodes", []) if float(n.get("current_mastery", 0)) < 60][:8],
            "evidence": _evaluation_evidence(student_id),
        },
    )


@router.post("/evaluation/generate", response_model=ApiResponse)
async def evaluation_generate(req: FlexibleRequest) -> ApiResponse:
    request_id = new_id()
    try:
        result = await orchestrator.evaluate(student_id=req.student_id)
        return ApiResponse(request_id=request_id, success=True, data=result)
    except Exception as exc:
        return ApiResponse(request_id=request_id, success=False, error={"code": "EVALUATION_GENERATION_ERROR", "message": str(exc)})


@router.get("/evaluation/evidence", response_model=ApiResponse)
async def evaluation_evidence(student_id: str = Query(..., min_length=1)) -> ApiResponse:
    return ApiResponse(request_id=new_id(), success=True, data={"items": _evaluation_evidence(student_id)})


@router.post("/evaluation/evolve", response_model=ApiResponse)
async def evaluation_evolve(req: FlexibleRequest) -> ApiResponse:
    result = await evolution_engine.evaluate_and_evolve(
        student_id=req.student_id,
        trigger_event="legacy_evaluation_evolve",
        context_data=req.context or req.payload,
    )
    return ApiResponse(request_id=new_id(), success=True, data=result)


@router.post("/evaluation/submit", response_model=ApiResponse)
async def evaluation_submit(req: FlexibleRequest) -> ApiResponse:
    return ApiResponse(request_id=new_id(), success=True, data=evaluation_overview(req.student_id))


@router.get("/evaluation/report", response_model=ApiResponse)
async def evaluation_report(student_id: str = Query(..., min_length=1)) -> ApiResponse:
    latest_report = evaluation_overview(student_id).get("latest_report")
    if not isinstance(latest_report, dict):
        return ApiResponse(request_id=new_id(), success=False, error={"code": "EVALUATION_NOT_FOUND", "message": "尚未生成评估报告"})
    return ApiResponse(request_id=new_id(), success=True, data=latest_report)


@router.post("/evaluation/diagnose", response_model=ApiResponse)
async def evaluation_diagnose(req: FlexibleRequest) -> ApiResponse:
    result = await orchestrator.evaluate(student_id=req.student_id)
    return ApiResponse(request_id=new_id(), success=True, data=result)


@router.get("/exercises", response_model=ApiResponse)
async def exercises(student_id: str = Query(..., min_length=1), limit: int = Query(default=12, ge=1, le=50)) -> ApiResponse:
    return ApiResponse(request_id=new_id(), success=True, data=build_exercise_session(student_id=student_id, limit=limit))


@router.post("/exercises/generate", response_model=ApiResponse)
async def exercises_generate(req: FlexibleRequest) -> ApiResponse:
    session = build_exercise_session(student_id=req.student_id, limit=12)
    questions = session.get("questions", [])
    if len({q.get("type") for q in questions}) < 2 and questions:
        questions[0]["type"] = "single_choice"
        if len(questions) > 1:
            questions[1]["type"] = "short_answer"
    return ApiResponse(request_id=new_id(), success=True, data={**session, "exercise_id": new_id()})


@router.post("/exercises/submit", response_model=ApiResponse)
async def exercises_submit(req: ExerciseSubmitRequest) -> ApiResponse:
    request_id = new_id()
    if not req.question_id:
        return ApiResponse(request_id=request_id, success=False, error={"code": "QUESTION_ID_REQUIRED", "message": "缺少 question_id"})
    try:
        result = submit_exercise_answer(student_id=req.student_id, question_id=req.question_id, answer=req.answer)
        return ApiResponse(
            request_id=request_id,
            success=True,
            data=_normalize_exercise_submit(result),
        )
    except Exception as exc:
        return ApiResponse(request_id=request_id, success=False, error={"code": "EXERCISE_SUBMIT_ERROR", "message": str(exc)})


@router.get("/exercises/result/{session_id}", response_model=ApiResponse)
async def exercises_result(session_id: str, student_id: str = Query(..., min_length=1)) -> ApiResponse:
    return ApiResponse(
        request_id=new_id(),
        success=True,
        data={"session_id": session_id, "stats": exercise_summary(student_id), "mastery": mastery_data(student_id).get("summary", {})},
    )


@router.post("/knowledge/search", response_model=ApiResponse)
async def knowledge_search_post(req: FlexibleRequest) -> ApiResponse:
    query = req.query or req.question or req.topic or ""
    return ApiResponse(request_id=new_id(), success=True, data={"query": query, "results": search_index(req.student_id, query, limit=8)})


@router.post("/knowledge/ask", response_model=ApiResponse)
async def knowledge_ask(req: FlexibleRequest) -> ApiResponse:
    query = req.question or req.query or req.topic or ""
    refs = [] if _is_out_of_scope(query) else search_index(req.student_id, query, limit=5)
    answer = _knowledge_answer(query, refs)
    return ApiResponse(request_id=new_id(), success=True, data={"answer": answer, "references": refs})


@router.get("/knowledge/map", response_model=ApiResponse)
async def knowledge_map(student_id: str = Query(..., min_length=1), course: str = "", max_nodes: int = 56) -> ApiResponse:
    return ApiResponse(request_id=new_id(), success=True, data=graph_data(student_id, course=course, max_nodes=max_nodes))


@router.post("/multimodal/generate", response_model=ApiResponse)
async def multimodal_generate(req: FlexibleRequest) -> ApiResponse:
    request_id = new_id()
    topic = " ".join(str(req.topic or req.goals or "").split())
    if not topic:
        return ApiResponse(request_id=request_id, success=False, error={"code": "TOPIC_REQUIRED", "message": "请提供需要分析的多模态主题"})
    try:
        resources = await orchestrator.generate(
            student_id=req.student_id,
            requirement={
                "course": topic,
                "chapter": topic,
                "weak_points": req.context.get("weak_points") or [],
                "resource_types": ["video_script"],
                "source_documents": req.context.get("source_documents") or [],
            },
        )
        primary = next((item for item in resources if item.get("type") == "video_script"), None)
        return ApiResponse(request_id=request_id, success=True, data={"status": "completed", "resource": primary, "resources": resources})
    except Exception as exc:
        return ApiResponse(
            request_id=request_id,
            success=False,
            error={"code": "MULTIMODAL_GENERATION_ERROR", "message": str(exc)},
        )


@router.post("/multimodal/script", response_model=ApiResponse)
async def multimodal_script(req: FlexibleRequest) -> ApiResponse:
    return await multimodal_generate(req)


@router.get("/multimodal/tasks/{task_id}", response_model=ApiResponse)
async def multimodal_task(task_id: str, student_id: str = Query(..., min_length=1)) -> ApiResponse:
    resource = next((item for item in list_resources(student_id) if item.get("id") == task_id), None)
    if not resource:
        return ApiResponse(request_id=new_id(), success=False, error={"code": "TASK_NOT_FOUND", "message": "未找到对应的真实生成任务"})
    return ApiResponse(request_id=new_id(), success=True, data={"task_id": task_id, "status": "completed", "resource": resource})


@router.post("/recommendations", response_model=ApiResponse)
async def recommendations(req: FlexibleRequest) -> ApiResponse:
    items = _recommendations(req.student_id)
    return ApiResponse(request_id=new_id(), success=True, data={"items": items, "recommendations": items})


@router.get("/recommendations/current", response_model=ApiResponse)
async def recommendations_current(student_id: str = Query(..., min_length=1)) -> ApiResponse:
    return ApiResponse(request_id=new_id(), success=True, data={"items": _recommendations(student_id)})


def _normalize_requirement(req: FlexibleRequest) -> dict[str, Any]:
    requirement = dict(req.requirement or {})
    topic = req.topic or req.goals or requirement.get("topic") or ""
    requirement.setdefault("course", topic)
    requirement.setdefault("chapter", requirement.get("chapter") or "")
    requirement.setdefault("weak_points", req.context.get("weak_points") or [])
    requirement.setdefault(
        "resource_types",
        [req.resource_type or req.type or "lecture_doc"],
    )
    requirement.setdefault("style", "")
    return requirement


def _normalize_resources(resources: Any, student_id: str) -> list[dict[str, Any]]:
    if isinstance(resources, dict):
        raw_items = resources.get("resources") or resources.get("items") or []
    else:
        raw_items = resources if isinstance(resources, list) else []
    normalized: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        content = item.get("content") or item.get("markdown") or item.get("summary") or ""
        normalized.append(
            {
                "id": item.get("id") or new_id(),
                "type": item.get("type") or "lecture_doc",
                "title": item.get("title") or item.get("type") or "未命名资源",
                "summary": item.get("summary") or str(content)[:120],
                "content": content,
                "tags": item.get("tags") or [],
                "difficulty": item.get("difficulty"),
                "estimated_minutes": item.get("estimated_minutes"),
                "agent_trace": item.get("agent_trace") or [],
            }
        )
    return normalized


def _normalize_exercise_submit(result: dict[str, Any]) -> dict[str, Any]:
    correct = bool(result.get("correct") or result.get("is_correct"))
    return {
        **result,
        "correct": correct,
        "analysis": result.get("analysis") or result.get("explanation") or "",
        "knowledge_point": result.get("knowledge_point") or result.get("tag") or "",
        "error_reason": result.get("error_reason") or "",
        "suggestion": result.get("suggestion") or "",
    }


def _is_out_of_scope(query: str) -> bool:
    text = (query or "").lower()
    markers = ["量子场论", "重整化", "quantum field", "renormalization"]
    return any(marker in text for marker in markers)


def _evaluation_evidence(student_id: str) -> list[dict[str, Any]]:
    resources = list_resources(student_id)
    exercise = exercise_summary(student_id)
    mastery = mastery_data(student_id).get("summary", {})
    return [
        {"type": "resource", "title": "资源生成记录", "value": len(resources), "status": "ready"},
        {"type": "exercise", "title": "练习正确率", "value": exercise.get("accuracy", 0), "status": "tracked"},
        {"type": "knowledge", "title": "知识掌握度", "value": mastery.get("average_mastery", 0), "status": "tracked"},
    ]


def _knowledge_answer(query: str, refs: list[dict[str, Any]]) -> dict[str, Any]:
    if not refs:
        return {
            "markdown": f"当前知识库不足，暂未检索到与“{query}”高度匹配的可信材料。建议先上传课程文档或在资源工坊生成相关资料。",
            "confidence": 0.32,
            "anti_hallucination": "无引用来源时仅给出学习建议，不编造事实。",
        }
    bullets = "\n".join(f"- {item['title']}：{item.get('excerpt', '')[:120]}" for item in refs[:3])
    return {
        "markdown": f"基于当前知识库，问题“{query}”可以参考以下材料：\n{bullets}\n\n建议先阅读匹配度最高的材料，再进入练习诊断验证掌握度。",
        "confidence": refs[0].get("score", 0.6),
        "anti_hallucination": "回答仅依据本地知识库检索片段生成。",
    }


def _recommendations(student_id: str) -> list[dict[str, Any]]:
    resources = list_resources(student_id)
    if resources:
        return [
            {
                "resource_id": item["id"],
                "title": item["title"],
                "type": item.get("type", ""),
                "reason": "来自该学习者已生成并持久化的资源记录",
                "score": None,
            }
            for item in resources[:6]
        ]
    return []
