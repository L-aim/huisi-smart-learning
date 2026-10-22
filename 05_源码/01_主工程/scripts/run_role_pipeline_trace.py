"""跑一次真实的九步角色编排，把 trace 落盘给 /api/orchestration/trace 读取。

为什么要这个脚本：`role_pipeline.py` 已经能在进程内按角色顺序调用九个 MCP 工具本体，
但编排目前不由线上主链路驱动（见交付报告 12.6 的边界说明）。所以「页面上的运行期记录」
只能来自一次显式执行的运行，把每一步的工具名、角色、传值来源落成 JSON，接口只读不跑。

用法（在 01_主工程/backend 目录下，需完整后端依赖）：

    python ../scripts/run_role_pipeline_trace.py demo 前端开发工程师
    python ../scripts/run_role_pipeline_trace.py demo          # 不给岗位 → 走 8 步

不指定岗位是合法用法：`get_role_competency` 没有默认岗位，空参必然 MISSING_ROLE_QUERY，
条件跳过比拿空参去撞失败更正确。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parents[1]  # 01_主工程
BACKEND_ROOT = PROJECT_ROOT / "backend"
WORKSPACE_ROOT = SCRIPT_PATH.parents[2]  # ICT

# 与 mcp_server/services.py 的计算口径一致：后端数据默认落在 backend/data。
os.environ.setdefault("DATA_DIR", str(BACKEND_ROOT / "data"))
for candidate in (str(BACKEND_ROOT), str(WORKSPACE_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)


def main() -> int:
    student_id = sys.argv[1] if len(sys.argv) > 1 else "demo"
    role_name = sys.argv[2] if len(sys.argv) > 2 else ""
    answer = sys.argv[3] if len(sys.argv) > 3 else "B"

    from app.agents.role_pipeline import (  # noqa: PLC0415
        MissingToolBinding,
        RolePipeline,
        ToolCallFailed,
        build_default_registry,
        missing_bindings,
    )
    from app.core.config import settings  # noqa: PLC0415

    registry = build_default_registry()
    missing = list(missing_bindings(registry))
    if missing:
        print(f"MISSING BINDINGS: {missing}")
        return 2

    pipeline = RolePipeline(registry=registry)
    runtime_ok = True
    runtime_error = None
    summary: dict[str, object] = {}
    try:
        summary = pipeline.run(student_id=student_id, answer=answer, role_name=role_name)
    except ToolCallFailed as exc:
        runtime_ok = False
        runtime_error = {"tool": exc.tool, "code": exc.code, "message": exc.message}
    except MissingToolBinding as exc:
        # 数据不足导致编排无法继续（例如画像里没有 weak_points）。
        # 这不是程序异常，而是「证据不够」的如实结论，照样落盘，别让页面以为跑完了。
        runtime_ok = False
        runtime_error = {"tool": "", "code": "MISSING_HANDOFF_DATA", "message": str(exc)}

    payload = {
        "source": "scripts/run_role_pipeline_trace.py",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "student_id": student_id,
        "role_name": role_name,
        "answer": answer,
        "ok": runtime_ok,
        "error": runtime_error,
        "steps": [
            {
                "index": step.index,
                "role": step.role,
                "tool": step.tool,
                "handoff": step.handoff,
                "failed": step.failed,
            }
            for step in pipeline.trace
        ],
        "summary_keys": sorted(summary.keys()) if isinstance(summary, dict) else [],
    }

    target = settings.data_path / "role_pipeline_trace.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"TRACE: {target}")
    print(f"ok={runtime_ok} steps={len(payload['steps'])}")
    for step in payload["steps"]:
        flag = "FAIL" if step["failed"] else "OK  "
        print(f"  {flag} {step['index']}. {step['role']:<12} {step['tool']:<24} {step['handoff']}")
    if runtime_error:
        print(f"STOPPED: {runtime_error}")
    return 0 if runtime_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
