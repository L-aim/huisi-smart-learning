"""多 Agent 运行时的假工具注册表。

**这些假实现的字段名必须与真实契约一致**，否则测试会撒谎（本项目已经吃过两次亏：
`weak_points` vs `weaknesses`、`stage_id` vs `current_stage.id`）。真实来源：

- `mcp_server/services.py:64`   `get_student_profile_data` → 顶层 `weaknesses`
- `mcp_server/services.py:216`  `get_project_status_data` → `{"student_id", "path": {...}}`，
  当前阶段在 `path.current_stage.id`
- `mcp_server/services.py:412`  `submit_exercise_answer_data` → `{"ok", "correct", "path_progress"}`
- `mcp_server/services.py:522`  `add_learning_branch_data` → `{"ok", "branch": {"id": ...}}`

返回信封与线上一致：`{"ok": True, "data": {...}}`。
用环境变量制造失败，便于验证「角色进程崩了，主控能停下来且其它角色不受影响」：

- `FAKE_FAIL_TOOL=search_knowledge`  让指定工具抛异常
- `FAKE_EMPTY_WEAK=1`                画像里不带 `weaknesses`（验证缺上文数据即中止）
"""
from __future__ import annotations

import os

STUDENT = {
    "student_id": "demo",
    "knowledge_base": {"level": "初学阶段"},
    "weaknesses": ["混淆用例图与需求访谈", "基础概念理解不牢固"],
    "learning_style": "视觉型",
}

PATH_PLAN = {
    "title": "软件需求分析与建模 · 三阶段学习路径",
    "current_stage": {"id": "stage-1", "title": "需求获取与建模基础", "status": "current"},
    "nodes": [
        {"id": "stage-1", "title": "需求获取与建模基础", "status": "current", "mastery": 0},
        {"id": "stage-2", "title": "用例建模与结构化表达", "status": "locked", "mastery": 0},
        {"id": "stage-3", "title": "需求文档与评审", "status": "locked", "mastery": 0},
    ],
}

QUESTIONS = [
    {
        "id": "generated:d3f1a6c2e8b94f5a9c7d21e604b8a3f7:0",
        "stem": "用例图主要用于刻画（ ）。",
        "type": "single_choice",
        "correct_answer": None,  # 线上接口不泄露答案
    }
]


def _fail_if(tool: str) -> None:
    if os.getenv("FAKE_FAIL_TOOL", "") == tool:
        raise RuntimeError(f"{tool} 模拟故障：上游服务不可用")


def get_role_competency_data(role_name: str = "", role_id: str = ""):
    _fail_if("get_role_competency")
    if not role_name and not role_id:
        return {"ok": False, "code": "MISSING_ROLE_QUERY", "message": "role_name 和 role_id 至少提供一个。"}
    return {
        "ok": True,
        "data": {
            "role": {"role_id": "job_002", "role_name": role_name or "前端开发工程师", "level": "中级"},
            "hard_skills": ["HTML/CSS/JS", "Vue", "React"],
        },
    }


def get_student_profile_data(student_id: str):
    _fail_if("get_student_profile")
    profile = dict(STUDENT)
    profile["student_id"] = student_id
    if os.getenv("FAKE_EMPTY_WEAK", "") == "1":
        profile["weaknesses"] = []
    return {"ok": True, "data": profile}


def search_knowledge_data(student_id: str, query: str):
    _fail_if("search_knowledge")
    if os.getenv("FAKE_BUSINESS_FAIL", "") == "search_knowledge":
        # 真实工具就有这种形态：HTTP 200、工具没抛异常，但业务层 ok=false
        # （线上实测过 `NO_QUESTION_BANK`）。
        return {
            "ok": False,
            "data": None,
            "error": {"code": "NO_QUESTION_BANK", "message": "该学生名下没有可用的题库资源，无法生成诊断练习。"},
        }
    return {
        "ok": True,
        "data": {
            "student_id": student_id,
            "query": query,
            "hits": [
                {
                    "resource_id": "resource:d3f1a6c2e8b94f5a9c7d21e604b8a3f7",
                    "title": "诊断练习：软件需求分析与建模",
                    "score": 0.615,
                }
            ],
            "hit_count": 1,
        },
    }


def get_project_status_data(student_id: str):
    _fail_if("get_project_status")
    return {"ok": True, "data": {"student_id": student_id, "path": PATH_PLAN}}


def get_exercise_session_data(student_id: str, limit: int = 3):
    _fail_if("get_exercise_session")
    return {
        "ok": True,
        "data": {"student_id": student_id, "source": "generated_question_bank", "questions": QUESTIONS},
    }


def submit_exercise_answer_data(student_id: str, question_id: str, answer: str):
    _fail_if("submit_exercise_answer")
    return {
        "ok": True,
        "correct": True,
        "submitted_answer": answer,
        "normalised_answer": answer,
        "data": {
            "student_id": student_id,
            "question_id": question_id,
            "correct": True,
            "path_progress": {
                "stage_id": "stage-1",
                "mastery": 33,
                "answered_count": 1,
                "correct_count": 1,
                "target_count": 3,
            },
        },
    }


def add_learning_branch_data(student_id: str, knowledge_node_id: str, title: str = ""):
    _fail_if("add_learning_branch")
    return {
        "ok": True,
        "data": {
            "student_id": student_id,
            "created": True,
            "branch": {"id": "branch-fake0001", "parent_stage_id": knowledge_node_id, "title": title},
        },
    }


def get_wrong_book_data(student_id: str):
    _fail_if("get_wrong_book")
    return {"ok": True, "data": {"student_id": student_id, "wrong_book_summary": {"total": 2, "correct": 0}}}


def get_learning_evaluation_data(student_id: str):
    _fail_if("get_learning_evaluation")
    return {
        "ok": True,
        "data": {
            "student_id": student_id,
            "evaluation": {
                "score": 22,
                "mastery": 0,
                "accuracy": 33.3,
                "evidence": {"total": 27},
                "confidence": {"level": "high", "label": "高"},
            },
        },
    }
