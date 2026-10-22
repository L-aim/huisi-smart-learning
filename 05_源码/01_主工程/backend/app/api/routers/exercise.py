from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.agents import Orchestrator
from app.core.ids import new_id
from app.schemas import ApiResponse, ExerciseAnswerRequest, GenerateRequest
from app.services.exercise_bank import (
    build_exercise_session,
    delete_all_wrong_records,
    delete_exercise_record,
    exercise_summary,
    submit_exercise_answer,
    wrong_book_summary,
)
from app.services.local_question_bank import build_local_question_bank, llm_ready


router = APIRouter(prefix="/api/exercise", tags=["exercise"])
exercise_orchestrator = Orchestrator()


@router.post("/generate-bank")
async def generate_bank(req: GenerateRequest):
    """Generate an exercise-only bank from the learner's explicit settings.

    This endpoint deliberately constrains orchestration to question_bank so the
    exercise centre never inherits the workshop's multi-resource selection.

    When no LLM is configured the endpoint falls back to a local template bank
    that carries `meta.local_template: true`, so the page can label it honestly
    instead of showing a red configuration error.
    """
    request_id = new_id()
    requirement = dict(req.requirement or {})
    requirement["resource_types"] = ["question_bank"]
    requirement["preferred_resources"] = ["question_bank"]
    requirement.setdefault("constraints", {})
    requirement["constraints"] = {
        **(requirement.get("constraints") or {}),
        "source": "exercise_custom_bank",
        "skip_quality_check": True,
    }

    if not llm_ready():
        item = build_local_question_bank(student_id=req.student_id, requirement=requirement)
        if req.stream:
            async def local_event_stream() -> AsyncIterator[str]:
                def pack(evt: dict) -> str:
                    return f"event: message\ndata: {json.dumps({'request_id': request_id, 'event': evt}, ensure_ascii=False)}\n\n"

                yield pack({"type": "start", "agents": ["local_question_bank"]})
                yield pack({"type": "agent_start", "agent": "local_question_bank", "title": "本地模板题库", "index": 0})
                yield pack({
                    "type": "agent_chunk",
                    "agent": "local_question_bank",
                    "text": "未检测到可用的大模型配置，改用本地模板题库（不调用任何外部模型）。",
                })
                yield pack({"type": "agent_done", "agent": "local_question_bank", "resource": item})
                yield pack({"type": "done"})

            return StreamingResponse(local_event_stream(), media_type="text/event-stream")

        return ApiResponse(
            request_id=request_id,
            success=True,
            data={"resources": [item], "mode": "local_template"},
        )

    if req.stream:
        async def event_stream() -> AsyncIterator[str]:
            try:
                async for evt in exercise_orchestrator.stream_generate(
                    student_id=req.student_id,
                    requirement=requirement,
                ):
                    yield f"event: message\ndata: {json.dumps({'request_id': request_id, 'event': evt}, ensure_ascii=False)}\n\n"
            except Exception as exc:
                yield f"event: error\ndata: {json.dumps({'request_id': request_id, 'error': str(exc)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    try:
        resources = await exercise_orchestrator.generate(student_id=req.student_id, requirement=requirement)
        return ApiResponse(request_id=request_id, success=True, data={"resources": resources})
    except Exception as exc:
        return ApiResponse(
            request_id=request_id,
            success=False,
            error={"code": "EXERCISE_BANK_GENERATE_ERROR", "message": str(exc)},
        )


@router.get("/session", response_model=ApiResponse)
async def session(
    student_id: str,
    limit: int = Query(default=12, ge=1, le=50),
    resource_ids: str = Query(default=""),
    refresh: int = Query(default=0, ge=0),
) -> ApiResponse:
    request_id = new_id()
    try:
        selected_resource_ids = [item.strip() for item in resource_ids.split(",") if item.strip()]
        data = build_exercise_session(student_id=student_id, limit=limit, resource_ids=selected_resource_ids, refresh_seed=refresh)
        return ApiResponse(request_id=request_id, success=True, data=data)
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "EXERCISE_SESSION_ERROR", "message": str(e)})


@router.post("/answer", response_model=ApiResponse)
async def answer(req: ExerciseAnswerRequest) -> ApiResponse:
    request_id = new_id()
    try:
        data = submit_exercise_answer(student_id=req.student_id, question_id=req.question_id, answer=req.answer)
        return ApiResponse(request_id=request_id, success=True, data=data)
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "EXERCISE_ANSWER_ERROR", "message": str(e)})


@router.get("/stats", response_model=ApiResponse)
async def stats(student_id: str) -> ApiResponse:
    request_id = new_id()
    try:
        return ApiResponse(request_id=request_id, success=True, data={"stats": exercise_summary(student_id)})
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "EXERCISE_STATS_ERROR", "message": str(e)})


@router.get("/wrong-book", response_model=ApiResponse)
async def wrong_book(student_id: str) -> ApiResponse:
    request_id = new_id()
    try:
        return ApiResponse(request_id=request_id, success=True, data=wrong_book_summary(student_id))
    except Exception as e:
        return ApiResponse(
            request_id=request_id,
            success=True,
            data={
                "groups": [],
                "records": [],
                "ability_radar": [],
                "tag_summary": [],
                "stats": {"total": 0, "correct": 0, "wrong": 0, "accuracy": 0, "weak_tags": [], "corrections": []},
                "warning": str(e),
            },
        )


@router.delete("/wrong-book/{record_id}", response_model=ApiResponse)
async def delete_wrong_book_record(record_id: str, student_id: str) -> ApiResponse:
    request_id = new_id()
    try:
        return ApiResponse(request_id=request_id, success=True, data=delete_exercise_record(student_id, record_id))
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "WRONG_BOOK_DELETE_ERROR", "message": str(e)})


@router.delete("/wrong-book", response_model=ApiResponse)
async def delete_wrong_book_records(student_id: str) -> ApiResponse:
    request_id = new_id()
    try:
        return ApiResponse(request_id=request_id, success=True, data=delete_all_wrong_records(student_id))
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "WRONG_BOOK_DELETE_ALL_ERROR", "message": str(e)})
