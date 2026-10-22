"""运行期工具调用留痕（只记录，不改变任何业务行为）。

背景：`scripts/run_role_pipeline_trace.py` 生成的 trace 只代表「显式跑那一次」，
而评委在页面上看到的应该是「真实用户操作留下的轨迹」。这个模块补的就是后者：

- 每次 HTTP 请求命中下面的路由映射表，就在 `settings.data_path/agent_trace_log.json`
  追加一条记录（环形保留最近 ``LIMIT`` 条）；
- 只读 `GET /api/orchestration/trace` 的 ``live`` 段读这份文件；
- 记录失败一律吞掉并写一条 warning 日志——留痕是旁路能力，不能因为它把业务请求搞挂。

映射表是「后端真实路由 → MCP 工具名」的对应关系，工具名与
`mcp_server/server.py` 的 9 个 `@mcp.tool()` 完全一致，页面据此把真实调用
挂回 Agent 拓扑上。
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings

logger = logging.getLogger("app.trace")

FILENAME = "agent_trace_log.json"
LIMIT = 80

# (method, path 前缀, 角色, MCP 工具名)
# 前缀匹配时取最长者，所以更具体的路径可以放在任意位置。
ROUTE_TOOL_MAP: tuple[tuple[str, str, str, str], ...] = (
    ("GET", "/api/profile/", "profile", "get_student_profile"),
    ("GET", "/api/knowledge/search", "knowledge", "search_knowledge"),
    ("GET", "/api/path/overview", "path", "get_project_status"),
    ("POST", "/api/path/stage/questions", "diagnose", "get_exercise_session"),
    ("POST", "/api/path/branch", "update", "add_learning_branch"),
    ("POST", "/api/exercise/answer", "diagnose", "submit_exercise_answer"),
    ("GET", "/api/exercise/wrong-book", "diagnose", "get_wrong_book"),
    ("GET", "/api/evaluate/overview", "update", "get_learning_evaluation"),
)

_HANDOFF_KEYS = ("student_id", "question_id", "stage_id", "knowledge_node_id", "role_name", "role_id", "query")

_LOCK = threading.Lock()


def _trace_path():
    return settings.data_path / FILENAME


def match_route(method: str, path: str) -> tuple[str, str] | None:
    """命中映射表就返回 (角色, 工具名)，否则 None。"""
    upper = (method or "").upper()
    best: tuple[int, str, str] | None = None
    for route_method, prefix, role, tool in ROUTE_TOOL_MAP:
        if route_method != upper or not path.startswith(prefix):
            continue
        if best is None or len(prefix) > best[0]:
            best = (len(prefix), role, tool)
    return (best[1], best[2]) if best else None


def derive_handoff(path: str, query_params: Any) -> dict[str, str]:
    """从查询串与路径里取出这次的入参，取不到就不写这个键。"""
    handoff: dict[str, str] = {}
    try:
        items = dict(query_params or {})
    except Exception:  # 非映射类型，宁可不记
        items = {}
    for key in _HANDOFF_KEYS:
        value = items.get(key)
        if value:
            handoff[key] = str(value)[:120]

    # /api/profile/<student_id>[/overview] 的学号在路径里
    if "student_id" not in handoff and path.startswith("/api/profile/"):
        segment = path[len("/api/profile/") :].split("/")[0]
        if segment and segment not in {"chat", "overview"}:
            handoff["student_id"] = segment[:64]
    return handoff


def record_request(method: str, path: str, query_params: Any, status_code: int) -> dict[str, Any] | None:
    """命中映射表就记一条。任何异常都只写日志，不向调用方抛。"""
    try:
        matched = match_route(method, path)
        if matched is None:
            return None
        role, tool = matched
        entry = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "method": (method or "").upper(),
            "path": path,
            "role": role,
            "tool": tool,
            "handoff": derive_handoff(path, query_params),
            "status": int(status_code),
            "ok": int(status_code) < 400,
            "source": "live",
        }
        _append(entry)
        return entry
    except Exception:  # 留痕是旁路能力，绝不 Swallow 业务
        logger.warning("trace record failed for %s %s", method, path, exc_info=True)
        return None


def _append(entry: dict[str, Any]) -> None:
    path = _trace_path()
    with _LOCK:
        entries: list[dict[str, Any]] = []
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    entries = loaded
                elif isinstance(loaded, dict) and isinstance(loaded.get("entries"), list):
                    entries = loaded["entries"]
            except Exception:
                entries = []  # 文件损坏就重新起一份，不阻塞业务
        entries.append(entry)
        entries = entries[-LIMIT:]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def read_entries(limit: int = 20) -> list[dict[str, Any]]:
    """读最近 ``limit`` 条真实调用记录，最新在前。"""
    path = _trace_path()
    if not path.exists():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("trace file unreadable: %s", path, exc_info=True)
        return []
    entries = loaded if isinstance(loaded, list) else loaded.get("entries", [])
    if not isinstance(entries, list):
        return []
    return list(reversed(entries[-max(1, limit) :]))


def count_entries() -> int:
    path = _trace_path()
    if not path.exists():
        return 0
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    entries = loaded if isinstance(loaded, list) else loaded.get("entries", [])
    return len(entries) if isinstance(entries, list) else 0
