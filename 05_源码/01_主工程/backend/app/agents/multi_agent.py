"""多 Agent 运行时：一个角色一个进程，主控只做调度与跨步传值。

与 `role_pipeline.py` 的区别（这是本模块存在的理由）：

| | `role_pipeline.py` | `multi_agent.py` |
| --- | --- | --- |
| 执行体 | 同一个进程里顺序调用函数 | **每个角色一个独立操作系统进程** |
| 隔离性 | 一个工具抛异常会影响整个调用栈 | 一个角色崩了，其它角色进程还活着 |
| 证据 | 步骤列表 | 每步记录 `pid`，可断言「角色 = 进程」 |
| 协作 | 共享内存变量 | 队列消息传递（每步一次往返） |

工具注册表用**模块名**注入：worker 自己 import 那个模块，取其中所有 `*_data` 函数
（对应 `mcp_server/services.py` 的线上工具本体）。这样父进程与子进程之间只传
可序列化的（工具名、参数、返回值），不传函数对象——Windows 上 `spawn` 也能用。
"""
from __future__ import annotations

import importlib
import multiprocessing as mp
import os
import queue as queue_module
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

READY = "ready"
RESULT = "result"

DEFAULT_TIMEOUT_S = 120.0
BRANCH_TITLE = "角色编排补充分支"

# spawn 在 Web 服务里有个坑：子进程会按 __main__ 的 spec 重新 import 主模块，
# 用 `python -m uvicorn app.main:app` 起服务时可能把服务再起一遍。
# Linux 容器用 fork 规避（子进程只 import 注册表、调文件型工具，不继承连接池）；
# Windows 只能用 spawn，所以入口一律要写 `if __name__ == "__main__"` 守卫。
DEFAULT_START_METHOD = "fork" if sys.platform.startswith("linux") else "spawn"


class MissingHandoffData(RuntimeError):
    """上一步的返回值里没有下一步需要的字段。"""

    def __init__(self, message: str):
        super().__init__(message)
        self.code = "MISSING_HANDOFF_DATA"


class ToolCallFailed(RuntimeError):
    """工具返回 ok=false。"""

    def __init__(self, tool: str, code: str, message: str):
        super().__init__(f"{tool} 失败 code={code} message={message}")
        self.tool = tool
        self.code = code or "TOOL_CALL_FAILED"


# ================================================================================
# 子进程侧
# ================================================================================
def _load_registry(module_name: str) -> Dict[str, Callable[..., Any]]:
    """从模块里取所有 `*_data` 函数，去掉后缀作为工具名。"""
    module = importlib.import_module(module_name)
    registry: Dict[str, Callable[..., Any]] = {}
    for name in dir(module):
        if name.startswith("_") or not name.endswith("_data"):
            continue
        value = getattr(module, name)
        if callable(value):
            registry[name[: -len("_data")]] = value
    return registry


def role_worker_main(role: str, registry_module: str, inbox, outbox) -> None:  # pragma: no cover
    """角色进程主循环：收一条任务、调一个工具、回一条结果，直到收到 None。"""
    try:
        registry = _load_registry(registry_module)
    except Exception as exc:  # noqa: BLE001
        outbox.put((READY, role, {"pid": os.getpid(), "error": f"{type(exc).__name__}: {exc}"}))
        return

    outbox.put((READY, role, {"pid": os.getpid(), "tools": sorted(registry)}))
    while True:
        message = inbox.get()
        if message is None:
            break
        step_id, tool, arguments = message
        started = time.time()
        try:
            function = registry.get(tool)
            if function is None:
                raise LookupError(f"角色 {role} 未绑定工具 {tool}")
            payload = function(**arguments)
            outbox.put(
                (
                    RESULT,
                    step_id,
                    {
                        "ok": True,
                        "payload": payload,
                        "elapsed_ms": round((time.time() - started) * 1000, 1),
                        "pid": os.getpid(),
                        "role": role,
                        "tool": tool,
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001
            outbox.put(
                (
                    RESULT,
                    step_id,
                    {
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                        "elapsed_ms": round((time.time() - started) * 1000, 1),
                        "pid": os.getpid(),
                        "role": role,
                        "tool": tool,
                    },
                )
            )


# ================================================================================
# 主控侧
# ================================================================================
@dataclass
class StepSpec:
    """一步编排：哪个角色、调哪个工具、参数怎么从上文算出来。"""

    role: str
    tool: str
    build: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
    optional: bool = False


@dataclass
class StepRecord:
    index: int
    role: str
    tool: str
    arguments: Dict[str, Any]
    ok: bool
    pid: Optional[int] = None
    elapsed_ms: float = 0.0
    handoff: str = ""
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "role": self.role,
            "tool": self.tool,
            "arguments": self.arguments,
            "ok": self.ok,
            "pid": self.pid,
            "elapsed_ms": self.elapsed_ms,
            "handoff": self.handoff,
            "error": self.error,
        }


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and "ok" in payload:
        return payload.get("data") if payload.get("ok") else payload
    return payload


def _deep_find(node: Any, key: str) -> Any:
    """广度优先找第一个同名键的值（返回结构层级不稳定时用它兜底）。"""
    level = [node]
    while level:
        nxt: List[Any] = []
        for item in level:
            if isinstance(item, dict):
                if key in item:
                    return item[key]
                nxt.extend(item.values())
            elif isinstance(item, list):
                nxt.extend(item)
        level = nxt
    return None


def _first_item(node: Any, key: str) -> Any:
    if isinstance(node, dict):
        value = node.get(key)
        if isinstance(value, list) and value:
            return value[0]
    return None


def _business_error(payload: Any) -> str:
    """工具返回了、但业务判定失败（形如 {"ok": false, "error": {"code", "message"}}）。"""
    if not isinstance(payload, dict) or payload.get("ok") is not False:
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        return f"{error.get('code') or 'TOOL_ERROR'}: {error.get('message') or ''}".strip()
    return str(error or "工具返回 ok=false，但未给出原因")


def _business_code(payload: Any) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and error.get("code"):
            return str(error["code"])
    return ""


def default_steps(role_name: str = "", role_id: str = "") -> List[StepSpec]:
    """九个步骤，按角色分工。第 0 步岗位对标是条件步骤。"""

    def _args(role_name: str = role_name, role_id: str = role_id):
        def build(context: Dict[str, Any]) -> Dict[str, Any]:
            args: Dict[str, Any] = {}
            if role_name:
                args["role_name"] = role_name
            if role_id:
                args["role_id"] = role_id
            return args

        return build

    def by_student(context: Dict[str, Any]) -> Dict[str, Any]:
        return {"student_id": context["student_id"]}

    def knowledge_args(context: Dict[str, Any]) -> Dict[str, Any]:
        weak = context.get("weak_point")
        if not weak:
            raise MissingHandoffData("画像里没有薄弱点（weaknesses），无法驱动检索——需要先补证据再编排")
        return {"student_id": context["student_id"], "query": str(weak)}

    def one_question(context: Dict[str, Any]) -> Dict[str, Any]:
        return {"student_id": context["student_id"], "limit": 1}

    def submit_args(context: Dict[str, Any]) -> Dict[str, Any]:
        question_id = context.get("question_id")
        if not question_id:
            raise MissingHandoffData("出题结果里没有 questions[0].id，无法提交作答")
        return {
            "student_id": context["student_id"],
            "question_id": str(question_id),
            "answer": str(context.get("answer") or "B"),
        }

    def branch_args(context: Dict[str, Any]) -> Dict[str, Any]:
        stage_id = context.get("stage_id")
        if not stage_id:
            raise MissingHandoffData("路径里没有 current_stage.id，无法挂分支")
        return {
            "student_id": context["student_id"],
            "knowledge_node_id": str(stage_id),
            "title": BRANCH_TITLE,
        }

    return [
        StepSpec("controller", "get_role_competency", _args(), optional=True),
        StepSpec("profile", "get_student_profile", by_student),
        StepSpec("knowledge", "search_knowledge", knowledge_args),
        StepSpec("path", "get_project_status", by_student),
        StepSpec("diagnose", "get_exercise_session", one_question),
        StepSpec("diagnose", "submit_exercise_answer", submit_args),
        StepSpec("update", "add_learning_branch", branch_args),
        StepSpec("review", "get_wrong_book", by_student),
        StepSpec("review", "get_learning_evaluation", by_student),
    ]


class MultiAgentRuntime:
    """主控：起进程、派任务、收结果、做跨步传值。"""

    def __init__(
        self,
        registry_module: str,
        timeout: float = DEFAULT_TIMEOUT_S,
        spawn_method: str = "spawn",
    ):
        self.registry_module = registry_module
        self.timeout = timeout
        self.ctx = mp.get_context(spawn_method)
        self.workers: Dict[str, Dict[str, Any]] = {}
        self.trace: List[StepRecord] = []

    # ---- 生命周期 ----
    def start(self, roles: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        result_queue = self.ctx.Queue()
        for role in roles:
            inbox = self.ctx.Queue()
            process = self.ctx.Process(
                target=role_worker_main,
                args=(role, self.registry_module, inbox, result_queue),
                name=f"agent-{role}",
                daemon=True,
            )
            process.start()
            self.workers[role] = {"process": process, "inbox": inbox, "pid": process.pid}
        self._result_queue = result_queue
        # 等所有角色报到，拿到真实 pid（子进程在 start() 时可能还没拿到）
        for _ in roles:
            kind, role, meta = self._recv()
            if kind != READY:
                raise RuntimeError(f"角色 {role} 启动异常")
            if meta.get("error"):
                raise RuntimeError(f"角色 {role} 注册表加载失败：{meta['error']}")
            self.workers[role]["pid"] = meta.get("pid") or self.workers[role]["pid"]
            self.workers[role]["tools"] = meta.get("tools") or []
        return self.workers

    def shutdown(self) -> None:
        for handle in self.workers.values():
            try:
                handle["inbox"].put(None)
            except Exception:  # noqa: BLE001
                pass
        for handle in self.workers.values():
            handle["process"].join(timeout=10)

    def _recv(self):
        try:
            return self._result_queue.get(timeout=self.timeout)
        except queue_module.Empty:
            raise TimeoutError(f"等待角色响应超过 {self.timeout} 秒")

    # ---- 执行 ----
    def run(
        self,
        student_id: str,
        answer: str = "B",
        role_name: str = "",
        role_id: str = "",
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        steps = default_steps(role_name=role_name, role_id=role_id)
        roles = sorted({spec.role for spec in steps})
        context: Dict[str, Any] = {"student_id": student_id, "answer": answer}
        if extra_context:
            context.update(extra_context)

        self.trace = []
        ok = True
        stop_reason: Dict[str, Any] = {}
        try:
            self.start(roles)
            for index, spec in enumerate(steps):
                # 条件步骤：参数 building 时算不出必要入参就跳过（不算失败）
                if spec.optional and not (role_name or role_id):
                    self.trace.append(
                        StepRecord(
                            index=index,
                            role=spec.role,
                            tool=spec.tool,
                            arguments={},
                            ok=False,
                            handoff="skipped: 未提供岗位标识",
                        )
                    )
                    continue
                try:
                    arguments = spec.build(context) if spec.build else {}
                except MissingHandoffData as exc:
                    ok = False
                    stop_reason = {
                        "tool": spec.tool,
                        "code": "MISSING_HANDOFF_DATA",
                        "message": str(exc),
                    }
                    self.trace.append(
                        StepRecord(
                            index=index,
                            role=spec.role,
                            tool=spec.tool,
                            arguments={},
                            ok=False,
                            handoff="aborted: 缺少上文数据",
                            error=str(exc),
                        )
                    )
                    break

                handle = self.workers[spec.role]
                handle["inbox"].put((index, spec.tool, arguments))
                kind, step_id, payload = self._recv()
                if kind != RESULT or step_id != index:
                    ok = False
                    stop_reason = {"tool": spec.tool, "code": "PROTOCOL_MISMATCH", "message": f"收到 {kind}/{step_id}"}
                    break

                record = StepRecord(
                    index=index,
                    role=spec.role,
                    tool=spec.tool,
                    arguments=arguments,
                    ok=bool(payload.get("ok")),
                    pid=payload.get("pid"),
                    elapsed_ms=float(payload.get("elapsed_ms") or 0.0),
                )
                raw_payload = payload.get("payload")
                business_error = _business_error(raw_payload)
                if record.ok and business_error:
                    # 工具没抛异常，但业务层回了 ok=false（如 NO_QUESTION_BANK）。
                    # 不把它当失败的话，后面只会显示「出题结果里没有题目 id」，把数据缺口说成代码问题。
                    record.ok = False
                    record.error = business_error
                if not record.ok:
                    record.error = record.error or str(payload.get("error") or "")
                    self.trace.append(record)
                    ok = False
                    stop_reason = {
                        "tool": spec.tool,
                        "code": _business_code(raw_payload) or "TOOL_CALL_FAILED",
                        "message": record.error,
                    }
                    break

                data = _unwrap(raw_payload)
                record.handoff = self._index(index, spec, data, context)
                self.trace.append(record)
        finally:
            self.shutdown()

        return {
            "ok": ok,
            "student_id": student_id,
            "steps": [record.as_dict() for record in self.trace],
            "context": context,
            "workers": {
                role: {"pid": handle.get("pid"), "tools": handle.get("tools") or []}
                for role, handle in self.workers.items()
            },
            "stop_reason": stop_reason,
        }

    # ---- 跨步传值 ----
    def _index(self, index: int, spec: StepSpec, data: Any, context: Dict[str, Any]) -> str:
        """把本步结果写进上下文，返回一句「为下一步提供了什么」。"""
        if spec.tool == "get_student_profile":
            weak = _first_item(data, "weaknesses") or _first_item(data, "weak_points")
            if weak:
                context["weak_point"] = weak
                return f"weaknesses[0] = {str(weak)[:40]}"
            return "画像里没有薄弱点"
        if spec.tool == "get_exercise_session":
            question_id = _first_item(data, "questions") or None
            if isinstance(question_id, dict):
                question_id = question_id.get("id")
            question_id = question_id or _deep_find(data, "id")
            if question_id:
                context["question_id"] = question_id
                return f"questions[0].id = {question_id}"
            return "出题结果里没有题目 id"
        if spec.tool == "get_project_status":
            current_stage = _deep_find(data, "current_stage")
            stage_id = current_stage.get("id") if isinstance(current_stage, dict) else None
            stage_id = stage_id or _deep_find(data, "stage_id")
            if stage_id:
                context["stage_id"] = stage_id
                return f"current_stage.id = {stage_id}"
            return "路径里没有当前阶段"
        if spec.tool == "submit_exercise_answer":
            correct = _deep_find(data, "correct")
            mastery = _deep_find(data, "mastery")
            if correct is not None:
                context["correct"] = correct
            if mastery is not None:
                context["mastery"] = mastery
            return f"correct = {correct} / mastery = {mastery}"
        if spec.tool == "add_learning_branch":
            branch = _deep_find(data, "branch_id") or _deep_find(data, "id")
            if branch:
                context["branch_id"] = branch
                return f"branch_id = {branch}"
            return "分支结果里没有 branch_id"
        return ""

    # ---- 自检 ----
    @staticmethod
    def missing_bindings(registry_module: str, steps: Optional[Sequence[StepSpec]] = None) -> List[str]:
        """静态检查：每个步骤的工具是否真的存在于注册表。"""
        registry = _load_registry(registry_module)
        steps = steps or default_steps()
        return [spec.tool for spec in steps if spec.tool not in registry]
