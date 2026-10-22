"""多 Agent 多进程 × **真实工具** 的验收脚本（本地，不需要起 Web 服务）。

与 `test_multi_agent.py` 的分工：
- `test_multi_agent.py` 用假注册表，能在任何环境跑，验证「进程隔离 / 传值 / 失败口径」共 27 项；
- 本脚本用真的 `mcp_server.services`（九个 `*_data`），验证同一套调度**确实能驱动线上工具**。

前置：本机装有 fastapi/pydantic/httpx（或把它们的目录放进 PYTHONPATH），
且 `01_主工程/backend/data` 里有 demo 的演示数据（题库 + 路径 + 画像）。

用法（Windows）：
    python test_multi_agent_real.py
退出码：0 = 九步全通；2 = 有步骤失败（会打印停在哪一步）；3 = 环境不满足（缺依赖/缺数据）。
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
ICT = os.path.dirname(PROJECT)
for path in (ICT, PROJECT, os.path.join(PROJECT, "backend"), os.path.join(PROJECT, "backend", "app", "agents"), HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

os.environ.setdefault("WORKSPACE_DIR", PROJECT)
REGISTRY = "mcp_server.services"
EXPECTED = [
    ("controller", "get_role_competency"),
    ("profile", "get_student_profile"),
    ("knowledge", "search_knowledge"),
    ("path", "get_project_status"),
    ("diagnose", "get_exercise_session"),
    ("diagnose", "submit_exercise_answer"),
    ("update", "add_learning_branch"),
    ("review", "get_wrong_book"),
    ("review", "get_learning_evaluation"),
]


def main() -> int:
    from multi_agent import MultiAgentRuntime

    try:
        missing = MultiAgentRuntime.missing_bindings(REGISTRY)
    except Exception as exc:  # noqa: BLE001
        print(f"SKIP 无法导入 {REGISTRY}：{type(exc).__name__}: {exc}")
        return 3
    if missing:
        print(f"SKIP 注册表缺工具：{missing}")
        return 3

    runtime = MultiAgentRuntime(REGISTRY, timeout=180)
    result = runtime.run(student_id="demo", answer="B", role_name="前端开发工程师")
    steps = result["steps"]
    workers = result["workers"]

    print(f"PARENT_PID {os.getpid()}")
    print(f"WORKERS {len(workers)} 个角色进程：" + " ".join(f"{role}={h['pid']}" for role, h in sorted(workers.items())))
    for step in steps:
        print(
            f"  {step['index']} {step['role']:<10} {step['tool']:<26} "
            f"ok={step['ok']} pid={step['pid']} {step['handoff'][:64]}"
        )
    if result["stop_reason"]:
        print(f"STOP {result['stop_reason']}")

    failures = []
    if len(workers) != 7:
        failures.append(f"角色数 {len(workers)} != 7")
    if len({h["pid"] for h in workers.values()}) != 7:
        failures.append("角色进程 pid 有重复")
    if os.getpid() in {h["pid"] for h in workers.values()}:
        failures.append("有角色跑在主控进程里")
    if len(steps) != 9 or not all(s["ok"] for s in steps):
        failures.append(f"步骤 {sum(1 for s in steps if s['ok'])}/9 通过")
    actual = [(s["role"], s["tool"]) for s in steps]
    if actual != EXPECTED:
        failures.append(f"步骤顺序不符：{actual}")

    if failures:
        print("FAIL " + "；".join(failures))
        return 2
    print(f"OK 9/9 通过，7 个角色 7 个真实进程；branch_id={result['context'].get('branch_id')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
