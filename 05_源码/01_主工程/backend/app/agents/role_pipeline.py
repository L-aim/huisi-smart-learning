"""P1-1 第三步：把「角色 + 工具绑定」从声明变成可执行的编排。

现状：`orchestrator.py` 里 6 个生成智能体已经声明了依赖的 MCP 工具，但没有任何代码
按这些声明去执行；`roles.py` 的 5 个角色也只是数据。

本模块给出真正可跑的编排：主控 + 5 角色依次执行，每一步都从上一步的真实返回值里取参数
（薄弱点 → 检索关键词，题目 id → 提交参数），并记录 trace 供前端与校验使用。

刻意做成「依赖注入」而不是直接 import 后端服务：
- 编排逻辑本身可以被单元测试覆盖（注入假实现即可），不依赖 fastapi / 数据库；
- 真实服务通过 `build_default_registry()` 延迟导入，接不上就抛错，不会静默降级。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .roles import ROLES


class MissingToolBinding(RuntimeError):
    """角色绑定的工具在注册表里找不到实现——宁可报错，也不静默跳过。"""


class ToolCallFailed(RuntimeError):
    """工具返回 ok=false。编排必须就地停住，不许跳过它继续跑。"""

    def __init__(self, tool: str, code: str, message: str) -> None:
        super().__init__(f"工具 {tool} 返回失败：code={code} message={message}")
        self.tool = tool
        self.code = code
        self.message = message


@dataclass
class Step:
    index: int
    role: str
    tool: str
    handoff: dict[str, Any] = field(default_factory=dict)
    failed: bool = False


@dataclass
class RolePipeline:
    registry: dict[str, Callable[..., Any]]
    trace: list[Step] = field(default_factory=list)

    # ---------- 工具调用 ----------

    def _call(self, role: str, tool: str, handoff: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        fn = self.registry.get(tool)
        if fn is None:
            raise MissingToolBinding(f"角色 {role} 绑定的工具 {tool} 没有实现")
        result = fn(**kwargs)
        if isinstance(result, dict) and result.get("ok") is False:
            self.trace.append(
                Step(index=len(self.trace) + 1, role=role, tool=tool, handoff=dict(handoff or {}), failed=True)
            )
            raise ToolCallFailed(
                tool,
                str(result.get("code") or "UNKNOWN"),
                str(result.get("message") or ""),
            )
        self.trace.append(Step(index=len(self.trace) + 1, role=role, tool=tool, handoff=dict(handoff or {})))
        return result

    # ---------- 取值助手 ----------

    @staticmethod
    def _unwrap(payload: Any) -> Any:
        """工具统一返回 {ok, data}，取 data；不是该结构就原样返回。"""
        if isinstance(payload, dict) and "data" in payload and ("ok" in payload or len(payload) == 2):
            return payload["data"]
        return payload

    @classmethod
    def _deep_find(cls, node: Any, key: str) -> Any:
        """广度优先找第一个同名键的值，避免对每种返回结构写死路径。"""
        queue: list[Any] = [node]
        while queue:
            current = queue.pop(0)
            if isinstance(current, dict):
                if key in current:
                    return current[key]
                queue.extend(current.values())
            elif isinstance(current, list):
                queue.extend(current)
        return None

    @classmethod
    def _first_item(cls, payload: Any, key: str) -> Any:
        found = cls._deep_find(cls._unwrap(payload), key)
        return found[0] if isinstance(found, list) and found else None

    # ---------- 编排 ----------

    def run(
        self, student_id: str, answer: str = "B", role_name: str = "", role_id: str = ""
    ) -> dict[str, Any]:
        self.trace = []

        # 主控：岗位能力口径。该工具没有「默认岗位」，空参必报 MISSING_ROLE_QUERY，
        # 所以只有拿到岗位标识时才走这一步，否则明确跳过，而不是拿空参去撞一个必然的失败。
        role_query = {key: value for key, value in (("role_name", role_name), ("role_id", role_id)) if value}
        role_matched = False
        if role_query:
            self._call("controller", "get_role_competency", dict(role_query), **role_query)
            role_matched = True

        profile = self._call(
            "profile", "get_student_profile", {"student_id": student_id}, student_id=student_id
        )
        # 真实返回里这个字段叫 weaknesses（见 mcp_server/services.py 的
        # get_student_profile_data），早期假测试用的是 weak_points，两个都认，但先取真实的那个。
        weak_point = self._first_item(profile, "weaknesses") or self._first_item(profile, "weak_points")
        if not weak_point:
            raise MissingToolBinding("画像里没有 weaknesses，无法驱动检索——需要先补证据再编排")

        knowledge = self._call(
            "knowledge", "search_knowledge", {"query": weak_point}, query=str(weak_point), student_id=student_id
        )

        path = self._call("path", "get_project_status", {"student_id": student_id}, student_id=student_id)
        # 真实返回是 {"student_id": ..., "path": path_overview(...)}，当前阶段在
        # path.current_stage.id；stage_id 是早期假数据的写法，保留作兜底。
        current_stage = self._deep_find(self._unwrap(path), "current_stage")
        stage_id = current_stage.get("id") if isinstance(current_stage, dict) else None
        if not stage_id:
            stage_id = self._deep_find(self._unwrap(path), "stage_id")

        session = self._call(
            "diagnose", "get_exercise_session", {"student_id": student_id}, student_id=student_id, limit=1
        )
        question = self._first_item(session, "questions")
        if not question or not question.get("id"):
            raise MissingToolBinding("出题结果里没有题目 id，无法提交")

        submitted = self._call(
            "diagnose",
            "submit_exercise_answer",
            {"question_id": question["id"]},
            student_id=student_id,
            question_id=question["id"],
            answer=answer,
        )

        branch = self._call(
            "update",
            "add_learning_branch",
            {"knowledge_node_id": stage_id, "title": str(weak_point)[:80]},
            student_id=student_id,
            knowledge_node_id=str(stage_id or ""),
            title=str(weak_point)[:80],
        )

        wrong_book = self._call("diagnose", "get_wrong_book", {"student_id": student_id}, student_id=student_id)

        evaluation = self._call(
            "update", "get_learning_evaluation", {"student_id": student_id}, student_id=student_id
        )

        return {
            "student_id": student_id,
            "role_matched": role_matched,
            "weak_point": weak_point,
            "knowledge_hits": len(self._deep_find(self._unwrap(knowledge), "results") or []),
            "stage_id": stage_id,
            "question_id": question["id"],
            "correct": self._deep_find(self._unwrap(submitted), "correct"),
            "branch_id": self._deep_find(self._unwrap(branch), "branch_id"),
            "wrong_count": len(self._deep_find(self._unwrap(wrong_book), "corrections") or []),
            "mastery": self._deep_find(self._unwrap(evaluation), "mastery"),
            "trace": [step.__dict__ for step in self.trace],
        }


def bound_tools() -> set[str]:
    return {tool for role in ROLES for tool in role["tools"]}


def build_default_registry() -> dict[str, Callable[..., Any]]:
    """把注册表接到 MCP 工具层的同一批实现上。

    刻意复用 `mcp_server.services` 而不是另写一套后端适配：
    那 9 个 `*_data` 函数就是线上 MCP 工具的本体，已经在云端逐个实测过；
    另写一套必然和工具层漂移，等于给自己造两份契约。

    前置条件（与 MCP 容器一致）：仓库根目录在 sys.path 上、WORKSPACE_DIR 指向工作区。
    """
    from mcp_server import services as mcp_services  # noqa: PLC0415 - 延迟导入

    return {
        "get_student_profile": mcp_services.get_student_profile_data,
        "get_role_competency": mcp_services.get_role_competency_data,
        "get_project_status": mcp_services.get_project_status_data,
        "search_knowledge": mcp_services.search_knowledge_data,
        "get_exercise_session": mcp_services.get_exercise_session_data,
        "submit_exercise_answer": mcp_services.submit_exercise_answer_data,
        "get_wrong_book": mcp_services.get_wrong_book_data,
        "get_learning_evaluation": mcp_services.get_learning_evaluation_data,
        "add_learning_branch": mcp_services.add_learning_branch_data,
    }


def missing_bindings(registry: dict[str, Callable[..., Any]]) -> Iterable[str]:
    return sorted(bound_tools() - set(registry))
