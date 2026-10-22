from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
MAIN_PROJECT_ROOT = WORKSPACE_ROOT / "01_主工程"
BACKEND_ROOT = MAIN_PROJECT_ROOT / "backend"
BACKEND_DATA_ROOT = BACKEND_ROOT / "data"
JOB_MODULE_ROOT = WORKSPACE_ROOT / "02_岗位能力模块" / "岗位图谱子系统"
JOB_DATA_PATH = WORKSPACE_ROOT / "02_岗位能力模块" / "结构化岗位画像.json"

# The original backend resolves DATA_DIR from the process working directory.
# Set a stable package-relative default before importing its service layer.
os.environ.setdefault("DATA_DIR", str(BACKEND_DATA_ROOT))
for import_root in (BACKEND_ROOT, JOB_MODULE_ROOT):
    import_path = str(import_root)
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from app.repo import get_user_events, list_resources  # noqa: E402
from app.services.exercise_bank import (  # noqa: E402
    build_exercise_session,
    exercise_summary,
    submit_exercise_answer,
    wrong_book_summary,
)
from app.services.knowledge_hub import search_index  # noqa: E402
from app.services.learning_state import (  # noqa: E402
    activity_feed,
    evaluation_overview,
    path_overview,
    profile_overview,
)
from app.services.path_progress import add_path_branch  # noqa: E402
from job_database import JobDatabase  # noqa: E402


_SAFE_STUDENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _success(data: dict[str, Any], *, source: str, data_mode: str) -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "error": None,
        "meta": {"source": source, "data_mode": data_mode},
    }


def _failure(code: str, message: str, *, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "data": None,
        "error": {"code": code, "message": message, "details": details or {}},
        "meta": {},
    }


def get_student_profile_data(student_id: str) -> dict[str, Any]:
    """Return an explainable student profile assembled by the existing service layer."""

    normalized_id = (student_id or "").strip()
    if not _SAFE_STUDENT_ID.fullmatch(normalized_id):
        return _failure(
            "INVALID_STUDENT_ID",
            "student_id 只能包含字母、数字、下划线或连字符，长度为 1-64。",
        )

    user_dir = BACKEND_DATA_ROOT / "users" / normalized_id
    if not user_dir.is_dir() or not (user_dir / "student.json").is_file():
        return _failure(
            "STUDENT_NOT_FOUND",
            f"未找到学生 {normalized_id} 的项目数据。",
            details={"student_id": normalized_id},
        )

    try:
        profile = profile_overview(normalized_id)
        events = get_user_events(normalized_id)
        stats = exercise_summary(normalized_id)
        recent_activity = activity_feed(normalized_id, limit=5)
        return _success(
            {
                "student_id": normalized_id,
                "basic_info": profile.get("learner", {}),
                "abilities": profile.get("dimensions", []),
                "weaknesses": profile.get("focus", {}).get("weak_points", []),
                "learning_summary": {
                    "profile_completeness": profile.get("completeness", 0),
                    "evidence_count": profile.get("evidence_count", 0),
                    "learning_event_count": len(events),
                    "exercise": stats,
                    "recent_activity": recent_activity,
                },
            },
            source="01_主工程/backend/data + app.services",
            data_mode="bundled_demo_data" if normalized_id == "demo" else "project_local_data",
        )
    except Exception as exc:
        return _failure(
            "STUDENT_PROFILE_SERVICE_ERROR",
            "读取学生画像时发生服务异常。",
            details={"type": type(exc).__name__, "message": str(exc)},
        )


def _job_database() -> JobDatabase:
    return JobDatabase(data_path=str(JOB_DATA_PATH))


def _experience_level(experience_requirement: str) -> dict[str, str]:
    """Infer a display level while preserving the exact source requirement."""

    match = re.search(r"(\d+)", experience_requirement or "")
    years = int(match.group(1)) if match else 0
    if years >= 5:
        level = "高级"
    elif years >= 3:
        level = "中高级"
    elif years >= 2:
        level = "中级"
    else:
        level = "初级/未明确"
    return {
        "level": level,
        "basis": "由 experience_require 字段映射，仅用于展示，不替代原始岗位要求。",
        "source_value": experience_requirement or "未明确",
    }


def get_role_competency_data(role_name: str = "", role_id: str = "") -> dict[str, Any]:
    """Query the existing structured job profiles by exact ID or name."""

    normalized_name = (role_name or "").strip()
    normalized_id = (role_id or "").strip()
    if not normalized_name and not normalized_id:
        return _failure("MISSING_ROLE_QUERY", "role_name 和 role_id 至少提供一个。")
    if len(normalized_name) > 100 or len(normalized_id) > 64:
        return _failure("INVALID_ROLE_QUERY", "岗位名称或岗位 ID 长度超出限制。")

    try:
        jobs = _job_database().get_all_jobs()
        matched = None
        match_type = ""
        if normalized_id:
            matched = next((job for job in jobs if job.job_id == normalized_id), None)
            match_type = "exact_role_id"
        if matched is None and normalized_name:
            matched = next((job for job in jobs if job.job_name == normalized_name), None)
            match_type = "exact_role_name"
        if matched is None and normalized_name:
            candidates = [job for job in jobs if normalized_name.lower() in job.job_name.lower()]
            if len(candidates) == 1:
                matched = candidates[0]
                match_type = "unique_partial_role_name"
            elif len(candidates) > 1:
                return _failure(
                    "AMBIGUOUS_ROLE_NAME",
                    "岗位名称匹配到多个结果，请改用完整岗位名称或岗位 ID。",
                    details={"candidates": [{"role_id": j.job_id, "role_name": j.job_name} for j in candidates[:10]]},
                )

        if matched is None:
            return _failure(
                "ROLE_NOT_FOUND",
                "未在结构化岗位画像中找到对应岗位。",
                details={"role_name": normalized_name, "role_id": normalized_id},
            )

        job = matched.model_dump() if hasattr(matched, "model_dump") else matched.dict()
        skills = job.get("skill_require") or {}
        experience = str(job.get("experience_require") or "")
        return _success(
            {
                "role_id": job.get("job_id"),
                "role_name": job.get("job_name"),
                "category": job.get("job_category"),
                "requirements": {
                    "hard_skills": skills.get("hard_skills", []),
                    "soft_skills": skills.get("soft_skills", []),
                    "education": job.get("education_require", []),
                    "certificates": job.get("certificate_require", []),
                    "experience": experience,
                },
                "skill_level": _experience_level(experience),
                "core_competencies": job.get("core_competency", []),
                "responsibilities": job.get("job_responsibility", []),
                "matching_basis": {
                    "match_type": match_type,
                    "query": {"role_name": normalized_name, "role_id": normalized_id},
                    "evidence_fields": [
                        "skill_require.hard_skills",
                        "skill_require.soft_skills",
                        "experience_require",
                        "core_competency",
                        "job_responsibility",
                    ],
                },
            },
            source="02_岗位能力模块/结构化岗位画像.json + JobDatabase",
            data_mode="project_structured_data",
        )
    except Exception as exc:
        return _failure(
            "ROLE_COMPETENCY_SERVICE_ERROR",
            "读取岗位能力时发生服务异常。",
            details={"type": type(exc).__name__, "message": str(exc)},
        )


def get_project_status_data(student_id: str) -> dict[str, Any]:
    """Optional MCP tool: expose the persisted learning-path project status."""

    normalized_id = (student_id or "").strip()
    if not _SAFE_STUDENT_ID.fullmatch(normalized_id):
        return _failure("INVALID_STUDENT_ID", "student_id 格式不正确。")
    if not (BACKEND_DATA_ROOT / "users" / normalized_id / "student.json").is_file():
        return _failure("STUDENT_NOT_FOUND", f"未找到学生 {normalized_id} 的项目数据。")
    try:
        path = path_overview(normalized_id)
        return _success(
            {"student_id": normalized_id, "path": path},
            source="01_主工程/backend/data + app.services.learning_state.path_overview",
            data_mode="bundled_demo_data" if normalized_id == "demo" else "project_local_data",
        )
    except Exception as exc:
        return _failure(
            "PROJECT_STATUS_SERVICE_ERROR",
            "读取项目状态时发生服务异常。",
            details={"type": type(exc).__name__, "message": str(exc)},
        )


# ---------------------------------------------------------------------------
# 动作型工具（2026-10-16 新增）
#
# 上面三个工具只做只读查询，撑不起「画像 → 检索 → 规划 → 诊断 → 路径更新」闭环。
# 以下六个服务函数复用后端已有的业务服务层，其中两个带写入语义：
#   submit_exercise_answer_data 会落作答记录、推进路径阶段进度并写学习事件；
#   add_learning_branch_data    会向当前学习路径写入一条知识补充分支。
# 写入落在容器内的 DATA_DIR（01_主工程/backend/data）。AgentArts 运行时是
# 会话级容器（空闲 15 分钟 / 最长 24 小时），写进去的数据在同一会话内有效，
# 容器回收后释放——这不是持久化存储。
# ---------------------------------------------------------------------------


def _ensure_student(student_id: str) -> dict[str, Any] | None:
    """Return a failure envelope when the student id is unusable, otherwise None."""

    if not _SAFE_STUDENT_ID.fullmatch(student_id):
        return _failure(
            "INVALID_STUDENT_ID",
            "student_id 只能包含字母、数字、下划线或连字符，长度为 1-64。",
        )
    if not (BACKEND_DATA_ROOT / "users" / student_id / "student.json").is_file():
        return _failure(
            "STUDENT_NOT_FOUND",
            f"未找到学生 {student_id} 的项目数据。",
            details={"student_id": student_id},
        )
    return None


def _data_mode(student_id: str) -> str:
    return "bundled_demo_data" if student_id == "demo" else "project_local_data"


def _question_bank_resource_ids(student_id: str) -> list[str]:
    """Mirror exercise_bank's own filter so the session is not empty by accident."""

    accepted = {"exercise_custom_bank", "path_stage_quiz"}
    resource_ids: list[str] = []
    for resource in list_resources(student_id):
        if resource.get("type") != "question_bank":
            continue
        requirement = (resource.get("meta") or {}).get("requirement") or {}
        constraints = requirement.get("constraints") or {}
        if str(constraints.get("source") or "") not in accepted:
            continue
        resource_id = str(resource.get("id") or "")
        if resource_id:
            resource_ids.append(resource_id)
    return resource_ids


def search_knowledge_data(student_id: str, query: str, limit: int = 5) -> dict[str, Any]:
    """检索学生学习资料库，返回带出处的引用片段。"""

    normalized_id = (student_id or "").strip()
    invalid = _ensure_student(normalized_id)
    if invalid is not None:
        return invalid

    normalized_query = (query or "").strip()
    if not normalized_query:
        return _failure("MISSING_QUERY", "query 不能为空。")
    if len(normalized_query) > 200:
        return _failure("INVALID_QUERY", "query 长度不能超过 200 个字符。")

    try:
        capped_limit = max(1, min(int(limit or 5), 10))
    except (TypeError, ValueError):
        capped_limit = 5

    try:
        results = search_index(normalized_id, normalized_query, limit=capped_limit)
        return _success(
            {
                "student_id": normalized_id,
                "query": normalized_query,
                "result_count": len(results),
                "results": results,
            },
            source="01_主工程/backend/app/services/knowledge_hub.search_index",
            data_mode=_data_mode(normalized_id),
        )
    except Exception as exc:
        return _failure(
            "KNOWLEDGE_SEARCH_ERROR",
            "检索学习资料库时发生服务异常。",
            details={"type": type(exc).__name__, "message": str(exc)},
        )


def get_exercise_session_data(student_id: str, limit: int = 5) -> dict[str, Any]:
    """从该学生已有的题库生成一组诊断练习题。"""

    normalized_id = (student_id or "").strip()
    invalid = _ensure_student(normalized_id)
    if invalid is not None:
        return invalid

    try:
        capped_limit = max(1, min(int(limit or 5), 20))
    except (TypeError, ValueError):
        capped_limit = 5

    try:
        resource_ids = _question_bank_resource_ids(normalized_id)
        session = build_exercise_session(
            student_id=normalized_id,
            limit=capped_limit,
            resource_ids=resource_ids,
        )
        questions = session.get("questions") or []
        if not questions:
            return _failure(
                "NO_QUESTION_BANK",
                "该学生名下没有可用的题库资源，无法生成诊断练习。",
                details={
                    "student_id": normalized_id,
                    "question_bank_resource_count": len(resource_ids),
                },
            )
        return _success(
            {
                "student_id": normalized_id,
                "source": session.get("source"),
                "question_count": len(questions),
                "questions": questions,
                "stats": session.get("stats"),
            },
            source="01_主工程/backend/app/services/exercise_bank.build_exercise_session",
            data_mode=_data_mode(normalized_id),
        )
    except Exception as exc:
        return _failure(
            "EXERCISE_SESSION_ERROR",
            "生成诊断练习时发生服务异常。",
            details={"type": type(exc).__name__, "message": str(exc)},
        )


_ANSWER_LETTERS_RE = re.compile(r"^[A-Ha-h](?:[,\s]*[A-Ha-h])*$")
_ANSWER_PREFIX_RE = re.compile(r"^\s*(?:选项|option|answer|正确选项)?\s*[:：]?\s*([A-Ha-h])\b")


def _normalise_answer_input(value: Any) -> Any:
    """把「B」「B. 选项全文」「选项B：xxx」「BC」「B,C」统一成字母串。

    华为云侧实证：模型容易把选项全文（如「B. 参与者与用例之间的交互关系」）
    当作 answer 传入，而后端判定是严格字符串比较，会把正确作答判成错误。
    """

    if isinstance(value, (list, tuple)):
        letters = [
            normalised
            for normalised in (_normalise_answer_input(item) for item in value)
            if isinstance(normalised, str) and normalised
        ]
        return ",".join(letters) if letters else ""

    text = str(value or "").strip()
    if not text:
        return ""

    compact = text.replace("，", ",").replace("、", ",").replace("；", ",").replace(" ", "")
    if _ANSWER_LETTERS_RE.match(compact):
        return ",".join(re.findall(r"[A-Ha-h]", compact.upper()))

    match = _ANSWER_PREFIX_RE.match(text)
    if match:
        return match.group(1).upper()
    return text


def submit_exercise_answer_data(student_id: str, question_id: str, answer: Any) -> dict[str, Any]:
    """提交一次作答：落记录、推进路径阶段进度、写学习事件。"""

    normalized_id = (student_id or "").strip()
    invalid = _ensure_student(normalized_id)
    if invalid is not None:
        return invalid

    normalized_question_id = str(question_id or "").strip()
    if not normalized_question_id:
        return _failure("MISSING_QUESTION_ID", "question_id 不能为空。")

    if isinstance(answer, (list, tuple)):
        raw_answer: Any = [str(item) for item in answer]
    else:
        raw_answer = str(answer or "").strip()
    if not raw_answer:
        return _failure("MISSING_ANSWER", "answer 不能为空。")

    normalized_answer = _normalise_answer_input(raw_answer)
    if not normalized_answer:
        return _failure("MISSING_ANSWER", "answer 不能为空。")

    try:
        result = submit_exercise_answer(
            student_id=normalized_id,
            question_id=normalized_question_id,
            answer=normalized_answer,
        )
        return _success(
            {
                "student_id": normalized_id,
                "question_id": normalized_question_id,
                "submitted_answer": raw_answer,
                "normalised_answer": normalized_answer,
                "correct": result.get("correct"),
                "correct_answer": result.get("correct_answer"),
                "analysis": result.get("analysis"),
                "path_progress": result.get("path_progress"),
                "stats": result.get("stats"),
            },
            source="01_主工程/backend/app/services/exercise_bank.submit_exercise_answer",
            data_mode=_data_mode(normalized_id),
        )
    except ValueError as exc:
        if str(exc) == "question_not_found":
            return _failure(
                "QUESTION_NOT_FOUND",
                "未找到该题目，请先用 get_exercise_session 取回有效题目 ID。",
                details={"question_id": normalized_question_id},
            )
        return _failure(
            "EXERCISE_SUBMIT_REJECTED",
            str(exc),
            details={"question_id": normalized_question_id},
        )
    except Exception as exc:
        return _failure(
            "EXERCISE_SUBMIT_ERROR",
            "提交作答时发生服务异常。",
            details={"type": type(exc).__name__, "message": str(exc)},
        )


def get_wrong_book_data(student_id: str) -> dict[str, Any]:
    """读取该学生的错题本与薄弱标签汇总。"""

    normalized_id = (student_id or "").strip()
    invalid = _ensure_student(normalized_id)
    if invalid is not None:
        return invalid

    try:
        summary = wrong_book_summary(normalized_id)
        return _success(
            {"student_id": normalized_id, **summary},
            source="01_主工程/backend/app/services/exercise_bank.wrong_book_summary",
            data_mode=_data_mode(normalized_id),
        )
    except Exception as exc:
        return _failure(
            "WRONG_BOOK_SERVICE_ERROR",
            "读取错题本时发生服务异常。",
            details={"type": type(exc).__name__, "message": str(exc)},
        )


def get_learning_evaluation_data(student_id: str) -> dict[str, Any]:
    """读取该学生的学习效果评估（指标、证据数与薄弱点建议）。"""

    normalized_id = (student_id or "").strip()
    invalid = _ensure_student(normalized_id)
    if invalid is not None:
        return invalid

    try:
        evaluation = evaluation_overview(normalized_id)
        return _success(
            {"student_id": normalized_id, "evaluation": evaluation},
            source="01_主工程/backend/app/services/learning_state.evaluation_overview",
            data_mode=_data_mode(normalized_id),
        )
    except Exception as exc:
        return _failure(
            "LEARNING_EVALUATION_SERVICE_ERROR",
            "读取学习效果评估时发生服务异常。",
            details={"type": type(exc).__name__, "message": str(exc)},
        )


def add_learning_branch_data(
    student_id: str,
    knowledge_node_id: str,
    title: str,
    description: str = "",
    mastery: float = 0,
) -> dict[str, Any]:
    """向当前学习路径写入一条知识补充分支（写入型操作）。"""

    normalized_id = (student_id or "").strip()
    invalid = _ensure_student(normalized_id)
    if invalid is not None:
        return invalid

    normalized_node_id = str(knowledge_node_id or "").strip()
    if not normalized_node_id:
        return _failure(
            "MISSING_KNOWLEDGE_NODE",
            "knowledge_node_id 不能为空；可先用 get_project_status 取当前路径节点 ID。",
        )

    clean_title = str(title or "").strip()
    if not clean_title:
        return _failure("MISSING_TITLE", "title 不能为空。")
    if len(clean_title) > 80:
        return _failure("INVALID_TITLE", "title 长度不能超过 80 个字符。")

    try:
        bounded_mastery = max(0.0, min(100.0, float(mastery or 0)))
    except (TypeError, ValueError):
        bounded_mastery = 0.0

    try:
        result = add_path_branch(
            normalized_id,
            knowledge_node_id=normalized_node_id,
            title=clean_title,
            description=str(description or "").strip(),
            mastery=bounded_mastery,
        )
        return _success(
            {
                "student_id": normalized_id,
                "created": bool(result.get("created")),
                "branch": result.get("branch"),
                "parent_stage": result.get("parent_stage"),
            },
            source="01_主工程/backend/app/services/path_progress.add_path_branch",
            data_mode=_data_mode(normalized_id),
        )
    except ValueError as exc:
        return _failure(
            "PATH_BRANCH_REJECTED",
            str(exc),
            details={"knowledge_node_id": normalized_node_id},
        )
    except Exception as exc:
        return _failure(
            "PATH_BRANCH_ERROR",
            "新增学习分支时发生服务异常。",
            details={"type": type(exc).__name__, "message": str(exc)},
        )

