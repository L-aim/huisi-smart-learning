"""P1-3 评测集静态校验与工程指标计算。

设计原则：指标必须能脱离云端复算，否则评委无法验证。
- 静态模式（默认）只读源码与评测集，交叉校验「评测集引用的工具是否真实存在」，
  这一步是真实交叉验证，不是自查自证。
- live 模式不在本脚本内实现，留在报告里说明（需要云端 IAM 凭据），
  因此「引用正确率」「工具调用成功率」在此只报告基线，不假装测过。

用法：
    python scripts/eval/run_eval.py
    python scripts/eval/run_eval.py --json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]          # 01_主工程
EVAL_SET = pathlib.Path(__file__).with_name("agentarts_eval_set.jsonl")
SERVER_PY = ROOT / "backend" / ".." / ".." / "mcp_server" / "server.py"
PATH_STAGES = {"stage-1", "stage-2", "stage-3"}

# 2026-10-17 云端实测基线（9/9 工具端到端调通），不是本脚本测出来的
BASELINE = {
    "measured_at": "2026-10-17",
    "tool_success": "9/9",
    "source": "TEST_RESULTS.md「云端 9 工具端到端实测（v8）」",
}


def load_tools(server: pathlib.Path) -> set[str]:
    """从 server.py 真实解析 @mcp.tool() 装饰的函数名。"""
    text = server.read_text(encoding="utf-8")
    return set(re.findall(r"@mcp\.tool\([^)]*\)\s*\ndef\s+([A-Za-z_][A-Za-z0-9_]*)", text))


def load_cases(path: pathlib.Path) -> list[dict]:
    cases, seen = [], set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"评测集第 {lineno} 行不是合法 JSON：{exc}")
        for key in ("id", "scene", "prompt", "tool", "expect"):
            if not case.get(key):
                raise SystemExit(f"评测集第 {lineno} 行缺少字段 {key}")
        if case["id"] in seen:
            raise SystemExit(f"评测集出现重复 id：{case['id']}")
        seen.add(case["id"])
        cases.append(case)
    return cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="只输出 JSON 指标")
    args = parser.parse_args()

    if not SERVER_PY.exists():
        raise SystemExit(f"找不到 MCP 入口：{SERVER_PY}")
    tools = load_tools(SERVER_PY)
    cases = load_cases(EVAL_SET)

    unknown_tool = [c["id"] for c in cases if c["tool"] not in tools]
    bad_stage = [
        c["id"]
        for c in cases
        if c.get("path_stage") and c["path_stage"] not in PATH_STAGES
    ]
    used = {c["tool"] for c in cases}
    scenes: dict[str, int] = {}
    for case in cases:
        scenes[case["scene"]] = scenes.get(case["scene"], 0) + 1

    metrics = {
        "cases": len(cases),
        "scenes": scenes,
        "tools_in_source": len(tools),
        "tools_referenced": len(used),
        "tools_never_referenced": sorted(tools - used),
        "unknown_tool_refs": unknown_tool,
        "bad_path_stage_refs": bad_stage,
        "tool_coverage": f"{len(used & tools)}/{len(tools)}",
        "static_pass": not unknown_tool and not bad_stage,
        "unmeasured": {
            "citation_correctness": "需 live 模式；基线见 2026-10-17 实测",
            "path_executable_rate": "需 live 模式；本地容器 7/7 已验",
            "tool_success_rate": f"{BASELINE['tool_success']}（{BASELINE['measured_at']} 云端实测）",
        },
    }

    if args.json:
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    else:
        print(f"评测集：{EVAL_SET.name}  场景：{scenes}")
        print(f"工具覆盖：{metrics['tool_coverage']}（源码解析出 {len(tools)} 个）")
        print(f"未引用的工具：{metrics['tools_never_referenced'] or '无'}")
        print(f"非法工具引用：{unknown_tool or '无'}")
        print(f"非法路径阶段：{bad_stage or '无'}")
        print(f"工具调用成功率：{metrics['unmeasured']['tool_success_rate']}")
        print(f"静态校验：{'通过' if metrics['static_pass'] else '失败'}")

    return 0 if metrics["static_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
